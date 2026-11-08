"""Equal-area comparisons of retained scene assets; no global deformation claims."""

import math
from contextlib import ExitStack


def compare_rasters(settings, body, scenes, payloads):
    try:
        import rasterio
    except ImportError:
        raise ValueError("Install requirements-geo.txt to enable raster comparisons") from None
    try:
        return _compare_rasters(settings, body, scenes, payloads)
    except rasterio.errors.RasterioError:
        raise ValueError(
            "Raster could not be decoded, projected or read within the configured limits"
        ) from None


def _compare_rasters(settings, body, scenes, payloads):
    try:
        import numpy as np
        import rasterio
        from rasterio.io import MemoryFile
        from rasterio.transform import from_origin
        from rasterio.warp import Resampling, reproject, transform_bounds
        from rasterio.windows import Window, from_bounds
    except ImportError:
        raise ValueError("Install requirements-geo.txt to enable raster comparisons") from None

    west, south, east, north = body.bbox
    left, bottom, right, top = transform_bounds("EPSG:4326", "EPSG:6933", west, south, east, north)
    resolution = 100.0
    width, height = math.ceil((right - left) / resolution), math.ceil((top - bottom) / resolution)
    if width < 1 or height < 1 or width * height > settings.raster_max_pixels:
        raise ValueError("Comparison exceeds the raster pixel budget; select a smaller area")
    transform = from_origin(left, top, resolution, resolution)
    with rasterio.Env(GDAL_CACHEMAX=32_000_000), ExitStack() as stack:
        grids = {}
        for name, data in payloads.items():
            memory = stack.enter_context(MemoryFile(data))
            src = stack.enter_context(memory.open())
            if not src.crs or src.count < 1:
                raise ValueError("Raster lacks a supported CRS or measurement band")
            bounds = transform_bounds("EPSG:4326", src.crs, *body.bbox, densify_pts=21)
            try:
                window = from_bounds(*bounds, transform=src.transform).round_offsets().round_lengths()
                window = window.intersection(Window(0, 0, src.width, src.height))
            except rasterio.errors.WindowError:
                raise ValueError("Selected area does not overlap both acquisitions") from None
            if window.width * window.height > settings.raster_max_pixels:
                raise ValueError("Native raster window exceeds the pixel budget; select a smaller area")
            values = src.read(1, window=window, masked=True).astype("float32").filled(np.nan)
            if values.size > settings.raster_max_pixels:
                raise ValueError("Native raster window exceeds the pixel budget")
            if name.endswith(("red", "nir")):
                scene_key, asset_key = name.split(".")
                bands = scenes[scene_key]["assets"][asset_key].get("raster_bands", [])
                if not bands or "scale" not in bands[0] or "offset" not in bands[0]:
                    raise ValueError("NDVI requires explicit reflectance scale and offset metadata")
                values = values * float(bands[0]["scale"]) + float(bands[0]["offset"])
            dst = np.full((height, width), np.nan, dtype="float32")
            reproject(
                values,
                dst,
                src_transform=src.window_transform(window),
                src_crs=src.crs,
                src_nodata=np.nan,
                dst_transform=transform,
                dst_crs="EPSG:6933",
                dst_nodata=np.nan,
                resampling=Resampling.bilinear if name.endswith(("red", "nir")) else Resampling.nearest,
                num_threads=1,
                warp_mem_limit=32,
            )
            grids[name] = dst
        if body.kind == "water":
            before, after = grids["before.water"], grids["after.water"]
            valid = np.isin(before, body.valid_classes) & np.isin(after, body.valid_classes)
            bwater, awater = np.isin(before, body.water_classes), np.isin(after, body.water_classes)
            result = {
                "water_before_hectares": float(np.count_nonzero(valid & bwater)),
                "water_after_hectares": float(np.count_nonzero(valid & awater)),
                "new_water_hectares": float(np.count_nonzero(valid & ~bwater & awater)),
                "receded_water_hectares": float(np.count_nonzero(valid & bwater & ~awater)),
                "water_classes": body.water_classes,
                "valid_classes": body.valid_classes,
                "interpretation": "Change in classified surface water within jointly valid pixels; not proof of flooding or damage",
            }
        else:
            indices = {}
            masks = {}
            for key in ["before", "after"]:
                red, nir, scl = grids[f"{key}.red"], grids[f"{key}.nir"], grids[f"{key}.scl"]
                masks[key] = np.isfinite(red) & np.isfinite(nir) & ((red + nir) > 0) & np.isin(scl, [4, 5, 6])
                indices[key] = np.divide(
                    nir - red, nir + red, out=np.full_like(red, np.nan), where=(red + nir) > 0
                )
            valid = masks["before"] & masks["after"]
            result = {
                "mean_ndvi_before": float(np.mean(indices["before"][valid])) if valid.any() else None,
                "mean_ndvi_after": float(np.mean(indices["after"][valid])) if valid.any() else None,
                "mean_ndvi_change": float(np.mean((indices["after"] - indices["before"])[valid]))
                if valid.any()
                else None,
                "interpretation": "Mean reflectance-derived NDVI change over jointly valid SCL classes 4,5,6; season, atmosphere and land management can affect it",
            }
        valid_count = int(np.count_nonzero(valid))
        if not valid_count:
            raise ValueError("No jointly valid measurement pixels in this area and acquisition pair")
        result.update(
            kind=body.kind,
            bbox=body.bbox,
            crs="EPSG:6933",
            resolution_m=resolution,
            valid_pixels=valid_count,
            grid_pixels=width * height,
            valid_coverage_fraction=valid_count / (width * height),
            valid_area_hectares=valid_count * resolution * resolution / 10000,
            before_id=scenes["before"]["id"],
            after_id=scenes["after"]["id"],
            before_acquired_at=scenes["before"]["acquired_at"],
            after_acquired_at=scenes["after"]["acquired_at"],
            limitations="100 m equal-area comparison; quality/nodata excluded; source resolution, class definitions and dates still limit interpretation",
        )
        return result

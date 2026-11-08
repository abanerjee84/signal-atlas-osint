"""Bounded optical/SAR catalogs, retained scene metadata and guarded raster assets."""

import hashlib
import json
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator

from .connectors.base import ProviderError
from .connectors.expanded import array, instant
from .models import Report, stamp, utcnow
from .monitoring_geo import geometry
from .monitoring_workflows import Input


class SceneSearch(Input):
    provider: str = Field(pattern="^(sentinel2|opera-water|opera-disturbance)$")
    bbox: list[float] = Field(min_length=4, max_length=4)
    start: datetime
    end: datetime
    max_cloud: float = Field(40, ge=0, le=100)
    limit: int = Field(20, ge=1, le=50)

    @field_validator("bbox")
    @classmethod
    def area(cls, b):
        w, s, e, n = b
        if not (-180 <= w < e <= 180 and -85 <= s < n <= 85) or e - w > 10 or n - s > 10:
            raise ValueError("Use a non-wrapping area of at most 10 by 10 degrees")
        return b

    @model_validator(mode="after")
    def dates(self):
        if (
            not self.start.tzinfo
            or not self.end.tzinfo
            or not self.start < self.end <= utcnow() + timedelta(minutes=1)
        ):
            raise ValueError("Use a past, ordered, timezone-aware acquisition interval")
        if self.end - self.start > timedelta(days=366):
            raise ValueError("Search at most one year of acquisitions per request")
        return self


def safe_asset(url):
    value = Report.safe_url(url)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.port not in {None, 443}:
        raise ValueError("Assets require public HTTPS")
    return value


def save_scene(database, provider, native_id, collection, acquired, shape, assets, metadata):
    shape = geometry(shape)
    identifier = hashlib.sha256(f"{provider}:{native_id}".encode()).hexdigest()
    with database.connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO monitoring_scenes VALUES(?,?,?,?,?,?,?,?,?)",
            (
                identifier,
                provider,
                str(native_id),
                collection,
                stamp(acquired),
                json.dumps(shape),
                json.dumps(assets),
                json.dumps(metadata),
                stamp(),
            ),
        )
        stored = dict(db.execute("SELECT * FROM monitoring_scenes WHERE id=?", (identifier,)).fetchone())
    for key in ("geometry", "assets", "metadata"):
        stored[key] = json.loads(stored[key])
    return stored


async def search_scenes(database, settings, http, body):
    items = []
    if body.provider == "sentinel2":
        data = await http.json(
            "GET",
            settings.imagery_search_url,
            params={
                "collections": "sentinel-2-l2a",
                "bbox": ",".join(map(str, body.bbox)),
                "datetime": f"{stamp(body.start)}/{stamp(body.end)}",
                "limit": body.limit,
                "query": json.dumps({"eo:cloud_cover": {"lte": body.max_cloud}}),
            },
        )
        rows = array(data, "features")
        for row in rows[: body.limit]:
            props = row["properties"]
            cloud = props.get("eo:cloud_cover")
            # Enforce locally as well; search implementations can ignore unsupported filters.
            if cloud is None or not 0 <= float(cloud) <= body.max_cloud:
                continue
            acquired = instant(props["datetime"])
            if not body.start <= acquired <= body.end:
                continue
            assets = {}
            for key, a in row.get("assets", {}).items():
                if key not in {"thumbnail", "visual", "red", "green", "blue", "nir", "scl"}:
                    continue
                try:
                    href = safe_asset(a["href"])
                except ValueError:
                    continue
                assets[key] = {
                    "href": href,
                    "type": str(a.get("type", ""))[:150],
                    "raster_bands": a.get("raster:bands", []),
                }
            items.append(
                save_scene(
                    database,
                    "sentinel2",
                    row["id"],
                    row.get("collection", "sentinel-2-l2a"),
                    acquired,
                    row["geometry"],
                    assets,
                    {
                        "cloud_percent": cloud,
                        "source_url": "https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a",
                        "classification": "scene_availability",
                        "license": "Sentinel data terms; Element 84 catalog",
                    },
                )
            )
        more = any(link.get("rel") == "next" for link in data.get("links", []))
    else:
        short = {"opera-water": "OPERA_L3_DSWX-S1_V1", "opera-disturbance": "OPERA_L3_DIST-ALERT-HLS_V1"}[
            body.provider
        ]
        data = await http.json(
            "GET",
            "https://cmr.earthdata.nasa.gov/search/granules.json",
            params={
                "short_name": short,
                "bounding_box": ",".join(map(str, body.bbox)),
                "temporal": f"{stamp(body.start)},{stamp(body.end)}",
                "page_size": body.limit,
                "sort_key": "-start_date",
            },
        )
        rows = array(data.get("feed", {}), "entry")
        for row in rows[: body.limit]:
            acquired = instant(row["time_start"])
            if not body.start <= acquired <= body.end:
                continue
            shape = None
            if row.get("boxes"):
                south, west, north, east = map(float, row["boxes"][0].split())
                if west < east:
                    shape = {
                        "type": "Polygon",
                        "coordinates": [
                            [[west, south], [east, south], [east, north], [west, north], [west, south]]
                        ],
                    }
            assets = {}
            for index, link in enumerate(row.get("links", [])):
                if link.get("inherited") or not link.get("href"):
                    continue
                rel = link.get("rel", "")
                if not rel.endswith(("browse#", "data#")):
                    continue
                try:
                    href = safe_asset(link["href"])
                except ValueError:
                    continue
                key = (
                    "thumbnail"
                    if rel.endswith("browse#")
                    else "water"
                    if "_B01_WTR.tif" in href
                    else f"asset-{index}"
                )
                assets[key] = {"href": href, "type": link.get("type", ""), "protected": "protected/" in href}
            items.append(
                save_scene(
                    database,
                    body.provider,
                    row["id"],
                    short,
                    acquired,
                    shape,
                    assets,
                    {
                        "source_url": f"https://search.earthdata.nasa.gov/search/granules?p={row.get('collection_concept_id', '')}",
                        "classification": "published_product_availability",
                        "native_name": row.get("producer_granule_id"),
                        "license": "NASA OPERA product terms; data access can require Earthdata",
                        "limitation": "Catalog metadata is not a detected flood, disturbance measurement or damage assessment",
                    },
                )
            )
        more = len(rows) >= body.limit
    return {
        "items": items,
        "truncated": more,
        "basis": "Acquisition-dated scene/product catalog records; not real-time imagery or inferred damage",
    }


def scene(database, identifier):
    with database.connect() as db:
        row = db.execute("SELECT * FROM monitoring_scenes WHERE id=?", (identifier,)).fetchone()
    if not row:
        raise ValueError("Scene is not retained; search the catalog first")
    return {**dict(row), **{k: json.loads(row[k]) for k in ["geometry", "assets", "metadata"]}}


async def asset_bytes(settings, http, item, key):
    asset = item["assets"].get(key)
    if not asset:
        raise ValueError("Scene does not provide the selected asset")
    href = safe_asset(asset["href"])
    host = urlsplit(href).hostname
    nasa_hosts = {"archive.podaac.earthdata.nasa.gov", "data.lpdaac.earthdatacloud.nasa.gov"}
    # These exact CDNs were returned by the two NASA public asset services.
    # SafeHTTP validates each hop and strips request headers before redirecting.
    nasa_cdns = {"deotb6e7tfubr.cloudfront.net", "d1nklfio7vscoe.cloudfront.net"}
    if host not in set(settings.imagery_asset_hosts) | nasa_hosts:
        raise ValueError("Asset host is not approved in OSINT_IMAGERY_ASSET_HOSTS")
    headers = {}
    if asset.get("protected"):
        if host not in nasa_hosts or not settings.earthdata_token:
            raise ValueError("This protected product needs OSINT_EARTHDATA_TOKEN")
        headers["Authorization"] = "Bearer " + settings.earthdata_token
    # A second SafeHTTP instance validates public DNS for the exact selected asset host.
    from .connectors.base import SafeHTTP

    bounded = SafeHTTP(
        settings.model_copy(
            update={"extra_allowed_hosts": [*settings.extra_allowed_hosts, host, *nasa_cdns]}
        ),
        http.client,
    )
    try:
        return await bounded.request(
            "GET",
            href,
            attempts=1,
            max_bytes=33_554_432,
            headers=headers,
            redirects=1 if host in nasa_hosts else 0,
        )
    except ProviderError:
        raise ValueError(
            "Asset unavailable or larger than the 32 MiB raster budget; select a smaller published product"
        ) from None


class RasterComparison(Input):
    before_id: str = Field(pattern="^[a-f0-9]{64}$")
    after_id: str = Field(pattern="^[a-f0-9]{64}$")
    kind: str = Field(pattern="^(water|ndvi)$")
    bbox: list[float] = Field(min_length=4, max_length=4)
    water_classes: list[int] = Field(default_factory=lambda: [1, 2], max_length=20)
    valid_classes: list[int] = Field(default_factory=lambda: [0, 1, 2, 3], max_length=50)

    @field_validator("bbox")
    @classmethod
    def area(cls, value):
        SceneSearch.area(value)
        if value[2] - value[0] > 2 or value[3] - value[1] > 2:
            raise ValueError("Raster comparisons are limited to 2 by 2 degrees")
        return value

    @model_validator(mode="after")
    def classes(self):
        if self.before_id == self.after_id:
            raise ValueError("Choose two different acquisitions")
        if self.kind == "water" and (
            not self.water_classes
            or not set(self.water_classes) <= set(self.valid_classes)
            or any(type(v) is not int or not 0 <= v < 250 for v in self.valid_classes)
        ):
            raise ValueError("Declare valid and water class codes from this product specification")
        return self

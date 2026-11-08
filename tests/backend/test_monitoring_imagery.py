from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.connectors.base import SafeHTTP
from backend.main import create_app
from backend.models import stamp, utcnow
from backend.monitoring_imagery import (
    RasterComparison,
    SceneSearch,
    asset_bytes,
    scene,
    search_scenes,
)
from backend.monitoring_rasters import compare_rasters
from backend.monitoring_recon import Lookup, finish, lookup, reserve


def search_body(provider="sentinel2"):
    return SceneSearch(
        provider=provider, bbox=[0, 0, 1, 1], start=utcnow() - timedelta(days=7), end=utcnow(), max_cloud=40
    )


async def test_stac_search_preserves_footprints_acquisition_quality_and_asset_roles(database, settings):
    when = utcnow() - timedelta(days=1)

    class HTTP:
        async def json(self, *args, **kwargs):
            return {
                "features": [
                    {
                        "id": "fixture-scene",
                        "collection": "sentinel-2-l2a",
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                        },
                        "properties": {"datetime": stamp(when), "eo:cloud_cover": 5},
                        "assets": {
                            "thumbnail": {"href": "https://example.org/preview.jpg", "type": "image/jpeg"},
                            "red": {
                                "href": "https://example.org/red.tif",
                                "raster:bands": [{"scale": 0.0001, "offset": 0}],
                            },
                            "cloud": {"href": "s3://example/private.jp2"},
                        },
                    }
                ],
                "links": [],
            }

    result = await search_scenes(database, settings, HTTP(), search_body())
    assert len(result["items"]) == 1
    row = result["items"][0]
    assert row["acquired_at"] == stamp(when) and row["metadata"]["classification"] == "scene_availability"
    assert set(row["assets"]) == {"thumbnail", "red"}
    assert scene(database, row["id"])["geometry"]["type"] == "Polygon"


async def test_cloud_filter_is_enforced_even_if_provider_ignores_it(database, settings):
    class HTTP:
        async def json(self, *args, **kwargs):
            return {
                "features": [{"id": "cloudy", "properties": {"datetime": stamp(), "eo:cloud_cover": 90}}],
                "links": [],
            }

    assert not (await search_scenes(database, settings, HTTP(), search_body()))["items"]


async def test_cmr_box_order_and_protected_product_are_not_a_flood_detection(database, settings):
    when = utcnow() - timedelta(days=1)

    class HTTP:
        async def json(self, *args, **kwargs):
            return {
                "feed": {
                    "entry": [
                        {
                            "id": "fixture-water",
                            "time_start": stamp(when),
                            "boxes": ["10 20 11 21"],
                            "collection_concept_id": "C-fixture",
                            "links": [
                                {
                                    "rel": "https://example.org/data#",
                                    "href": "https://archive.podaac.earthdata.nasa.gov/protected/fixture_B01_WTR.tif",
                                },
                                {
                                    "rel": "https://example.org/browse#",
                                    "href": "https://archive.podaac.earthdata.nasa.gov/public/fixture.png",
                                },
                            ],
                        }
                    ]
                }
            }

    result = await search_scenes(database, settings, HTTP(), search_body("opera-water"))
    row = result["items"][0]
    assert row["geometry"]["coordinates"][0][0] == [20, 10]
    assert row["assets"]["water"]["protected"]
    assert row["metadata"]["classification"] == "published_product_availability"
    assert "magnitude" not in row and "confidence" not in row


async def test_asset_download_refuses_unapproved_hosts_and_never_sends_nasa_token_to_them(settings):
    settings.earthdata_token = "synthetic-private-token"

    class HTTP:
        client = None

    item = {"assets": {"water": {"href": "https://example.org/protected/water.tif", "protected": True}}}
    with pytest.raises(ValueError, match="host"):
        await asset_bytes(settings, HTTP(), item, "water")


@pytest.mark.parametrize("destination", ["deotb6e7tfubr.cloudfront.net", "unapproved.example"])
async def test_nasa_asset_redirect_is_pinned_and_drops_bearer(settings, monkeypatch, destination):
    settings.earthdata_token = "synthetic-private-token"
    monkeypatch.setattr(
        "backend.connectors.base.socket.getaddrinfo",
        lambda *args: [(2, 1, 6, "", ("8.8.8.8", 443))],
    )
    calls = []

    def response(request):
        calls.append(request)
        if len(calls) == 1:
            assert request.headers["authorization"] == "Bearer synthetic-private-token"
            return httpx.Response(303, headers={"location": f"https://{destination}/asset"})
        assert "authorization" not in request.headers
        return httpx.Response(200, content=b"bounded-raster-fixture")

    item = {
        "assets": {
            "water": {
                "href": "https://archive.podaac.earthdata.nasa.gov/protected/fixture.tif",
                "protected": True,
            }
        }
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        http = SafeHTTP(settings, client)
        if destination == "unapproved.example":
            with pytest.raises(ValueError):
                await asset_bytes(settings, http, item, "water")
            assert len(calls) == 1
        else:
            assert await asset_bytes(settings, http, item, "water") == b"bounded-raster-fixture"
            assert len(calls) == 2


def raster_bytes(values, *, dtype="uint8", nodata=255):
    np = pytest.importorskip("numpy")
    from rasterio.io import MemoryFile
    from rasterio.transform import from_origin

    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            width=2,
            height=2,
            count=1,
            dtype=dtype,
            crs="EPSG:6933",
            transform=from_origin(0, 200, 100, 100),
            nodata=nodata,
        ) as dst:
            dst.write(np.array(values, dtype=dtype), 1)
        return mem.read()


def pair():
    return {
        key: {
            "id": key[0] * 64,
            "acquired_at": stamp(utcnow() - timedelta(days=2 if key == "before" else 1)),
            "assets": {},
        }
        for key in ["before", "after"]
    }


def area():
    pytest.importorskip("rasterio")
    from rasterio.warp import transform_bounds

    return list(transform_bounds("EPSG:6933", "EPSG:4326", 0, 0, 200, 200))


def test_water_change_has_equal_area_units_and_excludes_nodata(settings):
    scenes = pair()
    body = RasterComparison(before_id="b" * 64, after_id="a" * 64, kind="water", bbox=area())
    result = compare_rasters(
        settings,
        body,
        scenes,
        {"before.water": raster_bytes([[0, 1], [0, 255]]), "after.water": raster_bytes([[1, 1], [0, 255]])},
    )
    assert result["valid_pixels"] == 3
    assert result["new_water_hectares"] == pytest.approx(1)
    assert result["water_before_hectares"] == pytest.approx(1)
    assert result["water_after_hectares"] == pytest.approx(2)
    assert result["crs"] == "EPSG:6933" and "not proof" in result["interpretation"]


def test_ndvi_uses_explicit_scaling_and_joint_cloud_quality_masks(settings):
    scenes = pair()
    payloads = {}
    for key in ["before", "after"]:
        scenes[key]["assets"] = {
            band: {"raster_bands": [{"scale": 0.0001, "offset": 0}]} for band in ["red", "nir"]
        }
        red, nir = (200, 800) if key == "before" else (300, 700)
        payloads[f"{key}.red"] = raster_bytes([[red, red], [red, red]], dtype="uint16", nodata=0)
        payloads[f"{key}.nir"] = raster_bytes([[nir, nir], [nir, nir]], dtype="uint16", nodata=0)
        payloads[f"{key}.scl"] = raster_bytes([[4, 4], [4, 9]])
    body = RasterComparison(before_id="b" * 64, after_id="a" * 64, kind="ndvi", bbox=area())
    result = compare_rasters(settings, body, scenes, payloads)
    assert result["valid_pixels"] == 3 and result["mean_ndvi_change"] == pytest.approx(-0.2, abs=1e-5)
    scenes["before"]["assets"]["red"]["raster_bands"] = []
    with pytest.raises(ValueError, match="scale"):
        compare_rasters(settings, body, scenes, payloads)


def test_raster_pixel_budget_is_enforced_before_allocating_large_grids(settings):
    pytest.importorskip("rasterio")
    settings.raster_max_pixels = 1000
    body = RasterComparison(before_id="b" * 64, after_id="a" * 64, kind="water", bbox=[0, 0, 1, 1])
    with pytest.raises(ValueError, match="pixel budget"):
        compare_rasters(settings, body, pair(), {})


def test_lookup_budget_cache_and_failure_backoff(database, settings):
    settings.expansion_lookup_daily_budget = 1
    key, cached = reserve(database, settings, "dns", "example.org")
    assert key and cached is None
    with pytest.raises(ValueError, match="pending"):
        reserve(database, settings, "dns", "example.org")
    finish(database, key, {"answer": "synthetic"})
    assert reserve(database, settings, "dns", "example.org")[1] == {"answer": "synthetic"}
    with pytest.raises(ValueError, match="budget"):
        reserve(database, settings, "dns", "example.net")


async def test_passive_dns_and_rdap_connect_only_to_providers(settings):
    class HTTP:
        client = None

        async def json(self, *args, **kwargs):
            assert args[1] == "https://dns.google/resolve"
            return {
                "Status": 0,
                "Answer": [{"name": "example.org.", "type": 1, "TTL": 60, "data": "8.8.8.8"}],
            }

    http = HTTP()
    http.settings = settings
    result = await lookup(http, Lookup(kind="dns", target="example.org"))
    assert result["answers"][0]["data"] == "8.8.8.8"
    with pytest.raises(ValueError):
        await lookup(http, Lookup(kind="dns", target="http://127.0.0.1/path"))


def test_wikidata_retention_is_an_explicit_sourced_candidate_graph(settings, monkeypatch):
    async def response(http, body):
        return {
            "candidates": [
                {
                    "id": "Q123",
                    "label": "Synthetic candidate",
                    "source_url": "https://www.wikidata.org/wiki/Q123",
                    "relations": [
                        {
                            "property": "P127",
                            "relation": "owned by",
                            "value": {"id": "Q456"},
                            "references": [],
                            "rank": "normal",
                        }
                    ],
                }
            ],
            "basis": "Candidate matches only",
        }

    monkeypatch.setattr("backend.monitoring_workflows_api.lookup", response)
    with TestClient(create_app(settings)) as client:
        h = {"Authorization": "Bearer test-access-token"}
        result = client.post(
            "/api/monitoring/recon", headers=h, json={"kind": "wikidata", "target": "Synthetic candidate"}
        )
        assert result.status_code == 200
        data = result.json()
        graph = client.post(
            "/api/monitoring/enrichment/retain",
            headers=h,
            json={"lookup_id": data["lookup_id"], "candidate_id": "Q123"},
        )
        assert graph.status_code == 200 and graph.json()["status"] == "source_claim"
        db = client.app.state.database
        with db.connect() as conn:
            r = conn.execute("SELECT * FROM relationships").fetchone()
            assert r["status"] == "source_claim" and r["type"] == "owned by"
            assert conn.execute("SELECT COUNT(*) FROM relationship_evidence").fetchone()[0] == 1
        assert (
            client.post(
                "/api/monitoring/enrichment/retain",
                headers=h,
                json={"lookup_id": data["lookup_id"], "candidate_id": "Q999"},
            ).status_code
            == 422
        )

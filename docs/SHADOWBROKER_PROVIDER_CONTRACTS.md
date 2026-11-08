# Provider contracts for additional monitoring adapters

Checked 2026-11-08. Live probes below used anonymous HTTPS from the research environment. Raw public response samples are retained under the ignored `data/shadowbroker-research/contracts/` directory, not committed or seeded into application data. Live success establishes the response shape at this check, not an availability guarantee or redistribution permission.

## Earth Search Sentinel-2 STAC

**Endpoint:** `GET https://earth-search.aws.element84.com/v1/search` with `collections=sentinel-2-l2a`, `bbox=west,south,east,north`, optional `datetime=start/end`, `limit=1..bounded`. STAC POST search is also documented, but this review exercised GET. Anonymous HTTP 200 returned a GeoJSON FeatureCollection. Follow validated `links` with `rel=next` only within configured bounds.

Observed reduced Item (fields omitted, not invented):

```json
{
  "id": "S2B_30UXB_20261106_0_L2A",
  "collection": "sentinel-2-l2a",
  "properties": {
    "datetime": "2026-11-06T11:17:03.794000Z",
    "eo:cloud_cover": 70.329368,
    "proj:epsg": 32630
  },
  "assets": {
    "thumbnail": {
      "href": "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/30/U/XB/2026/11/S2B_30UXB_20261106_0_L2A/preview.jpg",
      "type": "image/jpeg",
      "roles": ["thumbnail"]
    }
  }
}
```

`geometry` is a Polygon in longitude/latitude, and `bbox` is a geographic extent, not a point fix. The same Item has `assets.red`, `green`, `blue`, `nir`, `scl`, and `visual`: HTTPS COG TIFF links. `visual` is `TCI.tif`, not a browser JPEG. `cloud` can be an `s3://` JP2 asset; do not assume every asset is anonymously HTTP-readable. Read band `raster:bands` scale, offset and nodata for calculations. A preview/card can use the JPEG; a scientific change workflow needs raster processing and quality masks. The API is best effort and v2 is beta; pin v1 for the current adapter. [Element 84 documentation](https://github.com/Element84/earth-search), [live collection contract](https://earth-search.aws.element84.com/v1/collections/sentinel-2-l2a).

## NASA CMR OPERA metadata and assets

**Endpoint:** `GET https://cmr.earthdata.nasa.gov/search/granules.json` with `short_name=OPERA_L3_DSWX-S1_V1`, `page_size=1`, `sort_key=-start_date`; add `bounding_box=west,south,east,north` and `temporal=start,end` for an area/time query. Anonymous HTTP 200 returned `feed.entry[]`.

Observed reduced entry:

```json
{
  "id": "G4404774363-POCLOUD",
  "producer_granule_id": "OPERA_L3_DSWx-S1_T38SNB_20261103T025335Z_20261104T003528Z_S1D_30_v1.0",
  "collection_concept_id": "C2949811996-POCLOUD",
  "boxes": ["32.4881991 44.9472568 33.48358 46.1290404"],
  "time_start": "2026-11-03T02:53:55.000Z",
  "time_end": "2026-11-03T02:54:15.000Z",
  "updated": "2026-11-07T16:40:06.802Z"
}
```

`boxes` order is **south west north east**, unlike a GeoJSON bbox. `links[]` identifies asset purpose by the `rel` suffix: `browse#`, `data#`, `metadata#`. The observed browse path is under `https://archive.podaac.earthdata.nasa.gov/podaac-ops-cumulus-public/OPERA_L3_DSWX-S1_V1/` and ends `_BROWSE.png`. Water mask `_B01_WTR.tif`, binary mask `_B02_BWTR.tif`, confidence `_B03_CONF.tif`, and diagnostic `_B04_DIAG.tif` links were under `podaac-ops-cumulus-protected/`, requiring authorized Earthdata asset access. Do not put provider credentials in public links or forward credentials across unvalidated redirect hosts.

Catalog membership proves scene/product availability, not detected flooding or a measured change. Keep an observation classified as a product/catalog record until a baseline and validated mask computation exist. Do not assign fake `magnitude=0` or fabricated confidence to metadata. Product short names/versions differ; discover current CMR collections rather than using one name for DSWx, DIST and DISP. [CMR search API](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html), [NASA OPERA product catalog](https://www.jpl.nasa.gov/go/opera/products/).

## Public camera contracts

| Provider | Endpoint / access | Current response contract and status |
| --- | --- | --- |
| NYC DOT | `GET https://webcams.nyctmc.org/api/cameras`; image link convention `/api/cameras/{id}/image` | Both research HTTP and web probes timed out. Upstream expects an array with `id`, `name`, `latitude`, `longitude`; this shape was source-inspected, **not live verified**. Keep opt-in and expose a source error rather than promising availability. |
| Caltrans | `GET https://cwwp2.dot.ca.gov/data/d4/cctv/cctvStatusD04.json`; per-district pattern `d{district}/cctv/cctvStatusD{district:02d}.json` | HTTP 200, 773 D4 cameras, about 2.5 MB. JSON root `data[]`, each wrapper has `cctv`. Details below. No key used in this check. |
| Singapore public data.gov.sg | `GET https://api.data.gov.sg/v1/transport/traffic-images` | HTTP 200; root `items[]`, each has `timestamp` and `cameras[]`. Each camera has `camera_id`, `timestamp`, `image`, `location.latitude`, `location.longitude`, optional `image_metadata`. Optional `x-api-key` improves limits; provider recommends once-per-minute calls. |
| Singapore direct LTA DataMall | `https://datamall2.mytransport.sg/ltaodataservice/Traffic-Imagesv2` | Separate API requiring `AccountKey`. Documented fields `CameraID`, `Latitude`, `Longitude`, `ImageLink`; image URLs are signed and expire after five minutes. Do not treat it as the same shape/auth as data.gov.sg. |

Observed Caltrans shape:

```json
{
  "data": [{"cctv": {
    "index": "1",
    "recordTimestamp": {"recordEpoch": "1769206788"},
    "location": {"district": "4", "locationName": "TV102 -- I-580 : West of SR-24", "latitude": "37.82539", "longitude": "-122.27291"},
    "inService": "true",
    "imageData": {
      "streamingVideoURL": "https://wzmedia.dot.ca.gov/D4/W580_JWO_24_IC.stream/playlist.m3u8",
      "static": {"currentImageURL": "https://cwwp2.dot.ca.gov/data/d4/cctv/image/tv102i580westofsr24/tv102i580westofsr24.jpg"}
    }
  }}]
}
```

Use a compound district/index ID. Parse string numbers and string booleans deliberately. `recordTimestamp` dates metadata and must not be assumed to be image capture time; the sample's metadata date was months older than this check. HLS playback requires a supported player and appropriate media/CORS behavior, not just a `<video>` URL in every browser. Preserve separate image, HLS and source-page links; user-triggered media is different from collection.

Observed Singapore record has `camera_id="2701"`, `timestamp="2026-11-08T04:00:24+08:00"`, `location={"latitude":1.447023728,"longitude":103.7716543}`, and an HTTPS JPEG under `images.data.gov.sg/api/traffic-images/`. Preserve the timezone and use the per-camera time, not the fetch time, when available. Neither feed supplies historical footage merely because metadata is retained.

[Caltrans CWWP2](https://dot.ca.gov/programs/traffic-operations/traveler-information/cwwp), [Singapore data.gov.sg API](https://developers.data.gov.sg/datasets?resultId=d_6cdb6b405b25aaaacbaf7689bcc6fae0&sort=downloadsCount), [LTA DataMall official API guide](https://datamall.lta.gov.sg/content/dam/datamall/datasets/LTA_DataMall_API_User_Guide.pdf), [NYC upstream adapter](https://github.com/BigBodyCobain/Shadowbroker/blob/e6e8f6e7b709666d128f5c25ccac144b0efda997/backend/services/cctv_pipeline.py).

## PSK Reporter XML and Maidenhead positions

**Endpoint:** `GET https://retrieve.pskreporter.info/query`; documented parameters include `senderCallsign` or `receiverCallsign`, `mode`, `flowStartSeconds` (negative relative seconds), `rronly`, `noactive`, `rptlimit`. No authentication used in a successful HTTP 200 check. Prefer a configured regional/callsign/frequency scope and a conservative cache interval instead of repeatedly downloading global reports.

Sanitized form of a real response record (callsigns removed):

```xml
<receptionReports>
  <lastSequenceNumber value="74579351691"/>
  <receptionReport receiverCallsign="REDACTED" receiverLocator="FM19EC"
    senderCallsign="REDACTED" senderLocator="JN01ug"
    frequency="18102077" flowStartSeconds="1794081675" mode="FT8" sNR="-10"/>
</receptionReports>
```

Attributes are strings: frequency is Hz, `flowStartSeconds` is an absolute Unix epoch in response records, `sNR` can be absent and must not default to a measured zero. XML may be namespaced. A composite of source, transmitting/receiving identity, time, frequency and mode can deduplicate records when no stable record ID exists. Use a hardened XML parser and reject malformed dates/coordinates.

The provider returned about 511 KB despite the test's `rptlimit=2`, so enforce local byte and record limits independently. Maidenhead locators are approximate grid squares, not receiver coordinates. Accept supported even-length grids case-insensitively; if converting a longer grid to four/six characters, explicitly reduce the precision label. A six-character cell is 5 arcminutes longitude by 2.5 arcminutes latitude. Plot a receiver grid only when a receiver locator exists; if using sender coordinates as fallback, preserve that different geographic role. [Official developer contract](https://pskreporter.info/pskdev.html).

## Global Fishing Watch events

**Endpoint:** `GET https://gateway.api.globalfishingwatch.org/v3/events` with server-side `Authorization: Bearer ...`. Example parameters: `datasets[0]=public-global-fishing-events:latest`, `start-date=YYYY-MM-DD`, `end-date=YYYY-MM-DD`, bounded `limit`, `offset`. Select the dataset explicitly for fishing, encounters, loitering, port visits or gaps. Tokens and provider terms are required; no authenticated live call was performed during this review.

Official response shape: `{entries:[{id,type,start,end,position:{lat,lon},vessel:{id,ssvid,name,flag,type},boundingBox,...}],limit,offset,nextOffset,total}`. Position values can be strings; validate latitude/longitude ranges rather than trusting example data. Event times are intervals; an event's representative position is not an AIS fix at every instant during that interval. Vessel IDs are provider IDs, while `ssvid` is a different identifier and must not silently become an IMO. Paginate with explicit request/row limits and report truncation. Dataset freshness varies; preserve provider event times rather than promising live fishing detection. [Events API](https://globalfishingwatch.org/our-apis/documentation/docs/v3/events), [get-all-events schema](https://globalfishingwatch.org/our-apis/documentation/docs/v3/events/get-all-events), [API access and non-commercial scope](https://globalfishingwatch.org/our-apis/documentation/).

## TinyGS

Upstream requests `https://api.tinygs.com/v1/satellitesWorldmap`, expecting a list of `{displayName|name,status,tags:{modulation:[],frequency:[]}}`. A prior anonymous probe in this review returned HTTP 403; no stable supported public API contract was established. Treat this endpoint as an optional provider integration requiring confirmed access, or accept an operator-configured authorized export. Do not present name-matched orbital propagation as a TinyGS reception or invent NORAD IDs from unverified names. Expose unavailable/stale state. [Pinned upstream adapter](https://github.com/BigBodyCobain/Shadowbroker/blob/e6e8f6e7b709666d128f5c25ccac144b0efda997/backend/services/tinygs_fetcher.py), [TinyGS project](https://tinygs.com/).

## WastewaterSCAN: use an authorized export

The upstream dashboard-internal catalog `https://storage.googleapis.com/wastewater-dev-data/json/plants.json` returned HTTP 200 with 193 plants and **11.65 MB**. This exceeds a typical bounded feed response and is not a documented supported API. A real plant record has `id`, `uid`, `uuid`, `name`, `site_name`, `point:{type:"Point",coordinates:[longitude,latitude]}`, polygon, `allow_download:false`, and other metadata; it does not use plain `latitude`/`longitude` fields. The existing upstream sample/time-series assumptions were not live verified.

The [official dashboard about/usage page](https://data.wastewaterscan.org/about/) instructs other database/research users to contact the project and specifies attribution. Public file reachability does not establish downstream data-use permission. Do not hardwire broad background collection or invent an official API. Implement a default-disabled **authorized JSON/CSV export import** with explicit provider/sample IDs, sample collection date, pathogen, measurement value, unit, non-detect/quality state, geographic reference, original source and permission basis. Require permission before automated downloads of time series, and preserve any per-site download restrictions. Export shape should be a local application contract, labelled as such, not advertised as provider-native.

## Shared access and evidence rules

- Validate both catalog and asset destinations against exact public host allowances; validate redirects independently, keep provider credentials server-side, and use no wildcard asset proxy.
- Preserve provider observation time, local receipt time, stable source IDs, geometry precision and asset purpose. No invented intensity, confidence, coordinates or successful-live status on an unavailable endpoint.
- STAC/CMR metadata adapters can be useful before raster processing exists, but label the result as imagery/product availability. Counts of scenes are not counts of detected events.
- Store provider payload fixtures only as bounded, sanitized tests or ignored research data. Runtime source catalogs should begin empty and fill through real collection or explicitly authorized imports.

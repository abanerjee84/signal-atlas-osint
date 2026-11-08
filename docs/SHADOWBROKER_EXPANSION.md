# Monitoring expansion: setup and operation

Signal Atlas now implements the 15 additions identified in the [ShadowBroker source review](SHADOWBROKER_ADDITIONAL_SOURCES.md). The implementation uses original provider adapters and the existing SQLite, worker, map and case workspace. It does not copy ShadowBroker application code.

The default registry contains **212 source definitions** and the monitoring workspace has **58 overlapping observation sublayers**, plus orbital and geographic reference views. These counts are configuration dependent. A registered definition is not a healthy feed; the dashboard reports successful collection separately. There are no seeded operational observations.

## Implemented coverage

| Addition | Implemented behavior | Access and interpretation |
| --- | --- | --- |
| Feodo and URLhaus | Typed C2 IP/port and malicious-URL observations, provider status and first/last evidence dates; infrastructure filters | Feodo is initially enabled; URLhaus requires `OSINT_URLHAUS_AUTH_KEY`. No connection is made to a listed host or malware URL. Unknown geography stays unlocated. |
| NWS warnings | Issued and expiring warnings with original polygons, severity and certainty | US and supported jurisdictions. Some warnings have no polygon and remain unlocated. Expired warnings leave the active map. |
| NOAA SWPC | Geomagnetic Kp samples and solar event classifications | Observations use the provider's UTC time. This is space weather, not local GNSS jamming detection. |
| More cameras | Caltrans districts, NYC traffic cameras and Singapore traffic snapshots | Direct public image loading is opt-in on inspection. A directory record does not verify a working stream; footage is not archived. |
| Infrastructure registries | Native WRI power-plant CSV ingestion; versioned power-plant, data-center, cable and supplier GeoJSON feeds/imports | WRI is an optional historical reference, versioned by file SHA-256. Other datasets require an authorized export or configured feed with version and license. No live operating status is inferred. |
| Area, route and entity watches | Spatial matching, per-entity transitions, cooldown, durable cursors, retained alerts and acknowledgment | Operator authenticated. Rules evaluate retained observations every 15 seconds. Missing telemetry does not imply an exit. |
| Global Fishing Watch activity | Apparent fishing, encounters, loitering, port visits and gaps | Existing `OSINT_GFW_API_TOKEN` required. Modeled/provider activity is separate from AIS positions and is not an illegality finding. |
| KiwiSDR and PSKReporter | Public receiver discovery and callsign-scoped FT8 reception metadata | Receiver directory availability varies. PSKReporter needs `OSINT_PSK_CALLSIGN`; Maidenhead grid centers are approximate. No tuning or audio recording. |
| TinyGS | Reception metadata adapter and authorized JSON/CSV import | Anonymous native access returned 403 during verification. Token/custom authorized endpoint or an export is required. Reception timestamps are mandatory; missing station positions stay unlocated. Orbital propagation is never substituted for reception. |
| Regional trains | Amtraker US passenger-train and Digitraffic Finland positions, timestamps and retained trails | Regional coverage only. These are independently scheduled 60-second telemetry feeds. |
| Air quality and volcanoes | OpenAQ v3 sensor/parameter/latest join; Smithsonian GVP Holocene volcano references | OpenAQ requires a key and selected location IDs. A volcano registry location is not a current eruption; a sensor sample is not national air quality. |
| Optical and SAR-derived product discovery | Sentinel-2 L2A STAC and NASA OPERA DSWx-S1/DIST-ALERT catalogs, dates, cloud filter, footprints and previews | Bounded operator searches. OPERA DSWx-S1 is a SAR-derived surface-water product. This is not a general raw-SAR or interferometry processing service. |
| Published assessments and measured change | Authorized published assessment geometry; paired water-class area and Sentinel-2 NDVI calculations | Optional raster dependencies and accessible raster assets required. Catalog availability alone produces no measurement or damage claim. |
| Passive recon and candidate enrichment | Third-party DNS, IANA-bootstrapped RDAP, certificate transparency, Wikidata and OFAC SDN candidates | Protected, cached and budgeted. Wikidata candidates can be explicitly retained as source-claimed graph relationships. No automatic identity merge or active target scan. |
| Supplier exposure, narratives and wastewater | Versioned supplier imports, cited spatial proximity, attributed EUvsDisinfo RSS and authorized wastewater samples | Proximity is not damage, interruption probability or a combined risk score. EUvsDisinfo is editorial reporting. Wastewater requires laboratory dates, units, analytes and permission basis. |

RIPE Atlas disconnected public-probe states are also available as a separate connectivity layer. An individual probe state does not establish a regional outage or its cause.

## Start or upgrade

1. Keep the existing `.env`; copy the settings you need from [`.env.example`](../.env.example). Set `OSINT_ADMIN_TOKEN` to enable private investigation actions.
2. Install the normal dependencies and build the frontend as described in [README](../README.md). For measured raster change, additionally run `.venv\Scripts\python.exe -m pip install -r requirements-geo.txt` on Windows, or `.venv/bin/python -m pip install -r requirements-geo.txt` on Linux.
3. Restart both API and collector. Database initialization automatically applies migration **013**, which adds watches, receipts, alerts, asset versions, scene metadata, analyses and lookup history. Back up the database before a production upgrade, following the existing operations guide.
4. Open the main dashboard at `/`. All 58 observation views are in **Intelligence layers**, below the base categories. Use **Observation layers (58)** to jump there, or type a topic such as `camera` in the shared layer search. Selecting a view draws its records on the existing map and opens the right-hand **Monitoring** panel. The main period and playhead also control monitoring history, bounded to seven days. **Monitoring tools → Investigations** contains watches, imagery, imports, recon and evidence. Enter the administrator token under **Operator access**; it stays in the current page and is not saved in local storage.
5. Check **Source health** and **Source coverage and setup**. Enable optional providers in the existing administrator source controls after configuring access.

The legacy `/monitoring.html` route is optional and has an explicit **Dashboard** return link. Both surfaces retain a bundled layer list if their catalog request fails, with a visible API error and retry. A 404 catalog response after an upgrade indicates that an older API process can still be running; restart both API and collector, not just the frontend. The Windows launcher now checks the monitoring catalog during startup. `powershell -File scripts/start.ps1 -Background` restarts this checkout's owned services without opening another browser or holding a terminal; `START.bat` retains the interactive start/stop flow.

Monitoring counts remain separate from dashboard event totals. Main-map geography filters currently select point observations; clear country/viewport restrictions to inspect warning polygons or unlocated evidence. This limitation is stated in the monitoring panel. The standalone workspace retains its own independent layer and time controls.

`OSINT_EXPANSION_ENABLED` sets initial defaults for newly registered sources. Persisted enable/disable choices take precedence after registration. Adding an ID to this environment setting does not override a previous administrator disable. Manual imagery and recon definitions are registered for protected operator actions, not background polling. Configured reference feeds are initially enabled.

Public defaults are Feodo, NWS, SWPC, Caltrans, NYC, Singapore, KiwiSDR, Amtraker, Digitraffic, volcano references and RIPE Atlas. Public availability remains a provider property, not a guarantee. Optional IDs include `urlhaus`, `openaq`, `psk_reporter`, `tinygs`, `gfw_events`, `wri_power_plants`, `euvsdisinfo`, `wastewater_export` and `published_assessments`.

Credential settings stay backend-only: `OSINT_URLHAUS_AUTH_KEY`, `OSINT_OPENAQ_API_KEY`, `OSINT_TINYGS_TOKEN`, the existing `OSINT_GFW_API_TOKEN`, and `OSINT_EARTHDATA_TOKEN`. Select OpenAQ locations with `OSINT_OPENAQ_LOCATION_IDS`. Caltrans districts default to `[3,4,7,11,12]`. PSKReporter is queried for one configured callsign at a ten-minute cadence.

## Watches, history and evidence

A watch accepts a WGS84 Polygon/MultiPolygon, buffered Point or route LineString/MultiLineString, or a source/entity identity. The UI can copy map bounds into a polygon. Geometry is validated; a point or route requires a positive radius. Layers and source/entity selectors can narrow the match.

**Enter** alerts on the first observed match and subsequent observed re-entry, subject to the source/entity cooldown. **New match** alerts on each matching new observation after cooldown. Defaults are a ten-minute cooldown and a one-hour maximum observation age. By default, evaluation starts after the watch is created; **Include fresh retained observations** permits an initial history evaluation. References, cameras, expired records, stale telemetry and unsupported regional point estimates do not trigger site alerts. Newer provider fixes take precedence over late older fixes.

Limits are 100 watches, 500 geometry vertices per watch, radius at most 1,000 km, and 2,000 receipts per watch per evaluation. A durable increasing receipt sequence survives history pruning; repeated evaluation does not duplicate alerts. Disabled rules stop evaluating. State older than 30 days is discarded, so a subsequent fresh match can be a new entry. Alerts retain the matched rule and observation independently of observation retention.

Entity history honors both acquisition/observation time and receipt time. Trails split at dateline crossings and gaps longer than 30 minutes; they do not interpolate across missing coverage. The map's observation window can be one hour, one day or seven days. Age and row limits can shorten available history.

Enter a case ID from the existing investigation workspace to use **Attach to case**. Observations, alerts, assets, scenes, lookups and analyses become immutable case snapshots with SHA-256 digests. Case retention is independent of monitoring-cache maintenance.

## Authorized infrastructure feeds and imports

Use **Infrastructure and supplier references** to import a GeoJSON FeatureCollection. Supply a source ID, dataset name, kind, source URL, version and license/permission text. Each feature needs a stable ID, name and WGS84 geometry. Supported kinds are `power-plant`, `data-center`, `cable` and `supplier`. Geometry is preserved, including cable lines and facility polygons.

This is a schema example only; it is not a real supplier or seeded dataset:

```json
{"type":"FeatureCollection","features":[{"type":"Feature","id":"example-facility","geometry":{"type":"Point","coordinates":[0,0]},"properties":{"name":"Schema example only","operator":"Example organization","sector":"Example sector","source_url":"https://example.org/dataset"}}]}
```

For scheduled ingestion, set `OSINT_REFERENCE_FEEDS` to definitions containing `source_id`, `name`, `url`, `license`, `version` and `kind`. Each URL must serve the same GeoJSON feature contract. Add its exact public HTTPS hostname to `OSINT_EXTRA_ALLOWED_HOSTS`; internal destinations and redirects remain blocked. Never embed credentials in URLs. The current import limit is 500 features and the browser file limit is 60 kB per batch. Split larger authorized exports, retaining stable source/entity/version values. Records marked `allow_download:false` are rejected.

**Asset exposure by proximity** compares at most 100 selected assets against 1,000 recent observations and reports the source URL, observation time and distance. It excludes references, stale/expired observations and unsupported regional point estimates. Bounds and truncation are disclosed; this is a cited spatial screen rather than an exhaustive dependency assessment.

## Wastewater, assessment and reception exports

Use **Authorized sample and assessment imports** for JSON or CSV, at most 200 records and 60 kB per browser upload. Permission basis is required and retained. These are application export schemas; they do not assert a public provider API exists. Permission blocks recorded by the deployment still apply to imports, even though disabling background polling does not prohibit an authorized manual export.

| Kind | Required content | Optional fields |
| --- | --- | --- |
| `wastewater_export` | GeoJSON feature properties `sample_id`, `sampled_at`, `analyte`, `unit`, `source_url`; `value` numeric or null | Geometry, `site`, `quality`, `allow_download` |
| `published_assessments` | Feature ID, geometry, properties `title`, `product_type`, `method`, `acquired_at`, `source_url` | `allow_download` |
| `tinygs` | Record `id` or `name`, `name`, and timezone-aware `lastSeen` or `timestamp` | `station:{name,latitude,longitude}`, `noradId`, `packets` |

JSON accepts a FeatureCollection, a records array, or `{records:[...]}` through the UI. Wastewater and published assessments use feature objects; TinyGS uses reception objects. Dates must declare a timezone or use numeric epoch timestamps where supported. Missing measurements remain null.

CSV uses the property names above as columns. Wastewater can use `sample_id` as its ID. Assessment rows need `id`. Geometry can be a JSON string in a properly quoted `geometry` cell, or `latitude` and `longitude` columns for a point. TinyGS CSV uses `station_name`, `latitude`, `longitude` and `norad_id` for station/NORAD metadata. Duplicate column names, excess records and malformed rows are rejected before storage.

Scheduled wastewater collection accepts the same FeatureCollection or a URL ending in `.csv`; configure `OSINT_WASTEWATER_URL` and `OSINT_WASTEWATER_LICENSE`. Scheduled published assessments accept a FeatureCollection through `OSINT_PUBLISHED_ASSESSMENTS_URL` and `OSINT_PUBLISHED_ASSESSMENTS_LICENSE`. Approve the exact host through `OSINT_EXTRA_ALLOWED_HOSTS` and enable the corresponding source. WastewaterSCAN's public site is not treated as blanket export permission; use data you are authorized to ingest. Laboratory sample time is separate from retrieval time.

## Imagery and raster measurements

Search Sentinel-2 optical imagery or OPERA surface-water/disturbance products by bbox and timezone-aware acquisition interval. Searches permit at most a 10 by 10 degree non-wrapping area, one year of dates and 50 results. Sentinel cloud cover is checked locally as well as requested from STAC. Scene metadata, footprints, source references and allowed asset links are retained. Dates are acquisition times, not live camera times. Previews are fetched through the protected backend and validated as bounded images.

Select two distinct acquisitions from the same collection in chronological order. **Water** needs OPERA DSWx-S1 water-class assets. **NDVI** needs Sentinel-2 red/NIR reflectance with explicit scale/offset metadata and SCL quality masks. Calculations align pixels on a 100 m EPSG:6933 equal-area grid; water area is reported in hectares, NDVI as a dimensionless index change. Joint valid coverage, source dates, grid size and method are retained. Cloud/nodata/unsupported classes are excluded. Water classes default to 1 and 2, with valid classes 0, 1, 2 and 3; the API permits explicit class declarations for compatible products.

Raster comparison requires `requirements-geo.txt`, at most a 2 by 2 degree bbox and `OSINT_RASTER_MAX_PIXELS` (default 4,000,000) for both native windows and output grid. Each downloaded asset is capped at 32 MiB. Full Sentinel tiles can exceed that cap; those requests fail with a size message rather than producing a result. This version does not perform remote range-window COG reads. Protected NASA rasters require an Earthdata token; the token is sent only to the approved NASA protected-asset hosts. NASA asset delivery allows one validated redirect to the two verified, exact CDN hostnames, stripping authorization before that hop. Additional asset hosts require exact entries in `OSINT_IMAGERY_ASSET_HOSTS` and must resolve to public HTTPS destinations.

OPERA disturbance catalogs and imported published assessments preserve the provider's classifications. They do not perform local disturbance detection. No global millimeter deformation, interferometric displacement, earthquake prediction or building-damage model is implemented or advertised. Vegetation and water changes need source-specific interpretation and do not establish a cause.

## Passive lookups and candidate graphs

DNS calls a public resolver; RDAP chooses a registry from the IANA bootstrap; certificates come from public CT records; Wikidata and OFAC produce candidate matches. No request connects to the investigated target host. Browser links to cited records are explicit analyst actions.

The default shared quota is 40 actions per UTC day across passive lookups, imagery searches and raster comparisons (`OSINT_EXPANSION_LOOKUP_DAILY_BUDGET`). Successful recon/raster results cache for 24 hours, catalog searches for one hour. Failed/pending requests consume budget and back off for two minutes. Cached reads do not consume another action. Shodan retains its existing separate budget.

**Retain candidate graph** requires choosing a returned Wikidata candidate. Ownership, parent, headquarters and country links are stored as source claims with the original lookup as evidence. They do not merge names into an existing verified identity. OFAC text matches are search candidates, not sanctions-clearance determinations.

## Retention and verification

Observation retention remains configurable, default seven days/250,000 rows. Daily maintenance also limits asset versions to the latest ten per source/entity, scenes to 5,000, alert history to 30 days, analyses to 90 days and lookup history to seven days. The default collector record budget is 1,000 records per source cycle, so large registries are bounded samples unless configured higher (maximum 5,000). Source health and response truncation must be consulted when assessing coverage.

Verification used temporary databases and synthetic test fixtures, never seeded production records:

- New provider/workflow/imagery tests cover schema parsing, authentication, atomic validation, dateline geometry, watch transitions and receipt retention, source permission handling, immutable case snapshots, candidate graphs, raster area/NDVI math, quality masks, quotas and asset-host rejection.
- Existing monitoring, API, connector, worker-contention, aviation-demand, satellite and source-permission checks passed.
- Seven Playwright monitoring workflows passed at desktop/mobile sizes, including failure and empty states. JavaScript unit tests and the production build passed.
- Live read-only normalization succeeded for Feodo (five current records), NWS, SWPC, Caltrans district 4, Singapore cameras, US/Finland trains, RIPE Atlas and GVP. Feodo's actual `port` schema is supported. Sentinel-2, OPERA-water and OPERA-disturbance catalog searches and image previews all returned HTTP 200 through the protected API.
- NYC timed out and the KiwiSDR mirror had a TLS connection failure during live probes. URLhaus returned 401 without credentials; TinyGS returned 403 anonymously. OpenAQ/GFW credentialed collection and protected NASA raster downloads were not live-validated. Raster calculations were verified with actual GeoTIFF fixtures; no real-world change measurement is claimed by that test.

Provider contract details and primary references are in [SHADOWBROKER_PROVIDER_CONTRACTS.md](SHADOWBROKER_PROVIDER_CONTRACTS.md). Earlier monitoring behavior and GNSS/Shodan configuration remain documented in [SHADOWBROKER_MONITORING.md](SHADOWBROKER_MONITORING.md).

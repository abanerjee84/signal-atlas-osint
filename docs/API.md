# API reference

The generated schema is at `/api/openapi.json`; the interactive development reference is at `/api/docs`. All data is JSON unless the event `format=geojson` parameter is selected.

| Method and path                                  | Behavior                                                                                      |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| `GET /api/health`                                | Database/API health, version and UTC time                                                     |
| `GET /api/status`                                | Per-source access/error/staleness, counts, worker heartbeat and storage                       |
| `GET /api/layers`                                | Nine SRS layers and associated sources                                                        |
| `GET /api/events`                                | Filtered bounded event page or GeoJSON FeatureCollection                                      |
| `GET /api/aviation/live`                         | Bounded current all-class aircraft snapshot with measured altitude, speed, age and collection state |
| `GET /api/events/{event_id}`                     | Event, source reports, review history and all time fields                                     |
| `GET /api/reports/{report_id}`                   | Original retained metadata and raw payload if still retained                                  |
| `GET /api/countries/{code}`                      | Country metadata, up to 50 matching events and news coverage sentiment                        |
| `GET /api/sentiment`                             | Report-based sample coverage, distributions, trends, regional scores and cited keyword groups |
| `GET /api/relations`                             | Bounded source-backed publisher/country and country co-mention connections                    |
| `GET /api/cyber/relations`                       | Source-backed cyber country context links and report counts                                   |
| `GET /api/military`                              | Official/media military evidence topics, cited reports, period comparisons and map networks   |
| `GET /api/timeline`                              | Up to 3,000 event count buckets                                                               |
| `GET /api/monitoring/catalog`                    | Monitoring sublayers, retained history limits, source status and workflow capabilities        |
| `GET /api/monitoring/frame`                      | Bounded retained observations at a UTC time; overlapping sublayers and truncation are stated  |
| `GET /api/v1/osint/search`                       | Protected by default; indexed investigation records in a `data`/`meta` envelope              |
| `GET /api/v1/osint/records/{record_id}`           | Investigation record with source and licensing context                                        |
| `GET/POST /api/v1/cases`                          | Protected case listing and creation                                                            |
| `GET /api/v1/cases/{case_id}`                     | Protected case with saved evidence and notes                                                   |
| `POST /api/v1/cases/{case_id}/evidence`           | Protected attachment of an existing evidence reference                                         |
| `POST /api/v1/cases/{case_id}/notes`              | Protected case note creation                                                                   |
| `GET /api/statistics`                            | Up to 3,300 daily/category aggregate records                                                  |
| `GET /api/sources`                               | Source metadata and access requirements without credentials                                   |
| `GET /api/anomalies`                             | Deterministic 6-hour volume comparisons with supporting event IDs                             |
| `POST /api/ai/analyze`                           | Protected source-grounded analysis; at most 30 explicit event IDs                             |
| `GET /api/ai/usage`                              | Local UTC daily budget, attempts and token accounting                                         |
| `POST /api/admin/social/reddit-browser`          | Protected bounded visible public Reddit capture import; no unattended browser collection      |
| `POST /api/admin/maintenance`                    | Protected retention and database maintenance                                                  |
| `POST /api/admin/connectors/{source_id}/refresh` | Protected request to schedule a collector job                                                 |
| `POST /api/admin/events/{event_id}/evidence`     | Protected evidence review under documented rules                                              |

## Shared filters

`categories` is a comma-separated list of layer category identifiers. `source_id` selects one exact source ID (lowercase letters, digits and underscores, at most 80 characters). `q` is a literal search string, at most 200 characters. `country` is an uppercase ISO alpha-2 code. `start` and `end` are timezone-qualified ISO 8601 values; reversed or timezone-less ranges are rejected. `bbox` is `west,south,east,north` in degrees and supports dateline crossing when west is greater than east. Missing coordinates do not match a bbox.

`aircraft_categories=4,5` restricts aviation observations to those classes with a valid reported ground track and location. It applies before pagination and to category totals and timeline queries; other categories are unaffected. The collector samples every class OpenSky reports (0-20), so any subset may be requested. The dashboard does not send the filter and filters classes in the browser instead, so switching the Countries-panel selector does not re-query. Omitting it retains the raw historical API view. The map draws the latest loaded observation per transponder, so map symbols are aircraft rather than a count of every historical observation.

The current Aviation view uses `/api/aviation/live` independently of the historical
page. It applies search, country, period and viewport filters, optionally restricts
aircraft to the requested emitter categories, and excludes positions older than ten
minutes. Current
snapshot IDs are stable transponder identifiers, not retained event IDs. Their
cards link to OpenSky; event analysis and evidence review require retained events.
Custom dates and historical playback continue to use `/api/events`. See
[aircraft, economic and AI changes](AIRCRAFT_ECONOMIC_AI_UPDATE.md).

`GET /api/anomalies/regional` compares the final six hours with the preceding six hours, requiring at least 20 observations in a trailing 72-hour baseline. Windows end at the selected `end` (capped at now), use `time_basis`, and preserve category/search/country/bbox filters. The selected `start` does not truncate baseline history. Responses disclose `window_end`, `time_basis`, counts and interpretation limits.

Layer health and source status share the same freshness calculation. A successful but stale source does not count as current; layer health includes a `stale` count and each affected source's status.

`time_basis` is `event` (occurrence with publication fallback), `published`, or `ingested`. Event/category/country/timeline endpoints use it for event filters. Sentiment always applies the start/end interval to each report's publication time and returns `period_basis=source_publication`.

Events accept `limit` 1..1,000 (default 500), `offset` 0..100,000, `format=json|geojson` and `order=latest|balanced`. Replies include `total`, `located_total`, `has_more`, `limit`, `offset`, `category_counts` and `selection`. Category counts cover all records matching period, geography and search, independently of enabled category checkboxes or the page limit. Absent categories have zero matches.

The default `latest` order sorts by descending selected time, then event ID. The dashboard uses `balanced`: it alternates categories and spreads each category across occupied 30-degree geographic cells before filling denser cells. This preserves other layers and regions when a frequent position feed exceeds the page limit. `selection` identifies `latest` or `layers_and_regions`; balanced order is not a purely chronological feed.

GeoJSON drops unlocated records from the returned page while retaining counts; clients must not assume that a short located page exhausts all matching reports. Offset pagination can shift as new records arrive; this release refreshes a bounded first page rather than guaranteeing snapshot-consistent pagination.

Sentiment accepts `kind=news|public|official`. It deduplicates original URLs and discloses the 5,000-URL bound and excluded language count. Timeline accepts `interval=hour|day`. All SQL values are bound parameters.

Example:

```text
/api/events?categories=environment,geopolitical&country=IN&start=2026-10-09T00:00:00Z&end=2026-10-10T00:00:00Z&limit=100
```

For a source-specific page, use `/api/events?categories=infrastructure&source_id=dshield&limit=20`. The optional [MCP adapter](MCP.md) provides bounded versions of common API reads and protected case actions to local MCP hosts; the HTTP API remains the full integration surface.

## Protected requests

Send `Authorization: Bearer <OSINT_ADMIN_TOKEN>`. This token is separate from provider credentials. With no configured token the endpoints return 503; an incorrect/missing token returns 401. The application supplies one administrator role; individual accounts and scoped permissions are not implemented.

AI body:

Successful responses carry `output_mode=structured|draft` and
`citation_validation=validated|not_validated`. Structured claims retain schema
and citation membership checks; invalid citation IDs are rejected. A plain-text
or malformed structured reply is returned as `draft_text` with empty claims and
explicit limitations. Context references are not citations supporting the draft.
Fenced or prose-wrapped JSON can be recovered locally without another model call.

```json
{
  "question": "Summarize these source reports and identify contradictory claims.",
  "event_ids": [],
  "filters": {
    "categories": ["geopolitical"],
    "country": "IN",
    "q": "",
    "time_basis": "event"
  }
}
```

An empty ID list selects the newest bounded matching set. IDs must refer to existing events. Output has `claims` with `sourced_fact|interpretation|contradiction`, exact event/report citations, `limitations`, server-bound `references`, actual model identifier, UTC analysis time and `cached`. Schema or citation failure returns 502. Missing provider configuration/model access returns 503; local or provider quota failure returns 429. There is no code or SQL generation/execution endpoint.

Evidence review body fields are `confidence`, `basis` (30..2,000 characters), `report_ids` (1..20), `independent_sources_confirmed` and `contradiction_confirmed`. All report IDs must belong to the event. Corroborated requires two publisher hosts and explicit independence confirmation; Disputed requires two reports and conflict confirmation; Verified requires a qualifying provider-reviewed report. Reviews persist with timestamps and references.

Request bodies, including chunked bodies, are capped at 64 KiB. Per-peer application rate limit is 120 requests/minute with a bounded counter; production Nginx adds shared rate limits. Invalid inputs return 422, missing records 404, database failure 503 and oversized bodies 413. Provider failures do not clear stored data.

## Social and military evidence

`GET /api/sentiment?kind=public` returns up to 2,000 unique platform post IDs and the latest 100 source texts, with a 50-post discussion graph. `platform=all|reddit|x|youtube` selects a platform; `geography=mentions|origin` chooses country context or declared origins. `kind=news&platform=youtube` returns upload wording, not viewer comments. Public discussions have a 24-hour local TTL and snapshots are replaced after successful collection. Source failures remain visible in status.

`GET /api/relations` and `GET /api/military` apply report publication dates and literal search; country/bbox selection uses named country context and country-centre geometry. These endpoints read up to 1,000 distinct report URLs, independently of physical-layer checkbox selection. The relations endpoint returns up to 100 evidenced curves. Each edge carries `sentiment` (mean `sentiment_score` over the reports on that edge, `null` when none were scored) and `sentiment_samples`; the map tints each travelling pulse by that value on the same ramp as the sentiment heatmaps. That tone describes the wording carried by the edge, not opinion of the country receiving it. Military topics can overlap; each has a bounded report list, explicit event IDs, country context and an independently selectable map network. Period comparisons are publication counts for earlier/later halves, not operational trends.

`GET /api/events` returns aviation records with `aircraft_callsign`,
`aircraft_track_deg` (reported ground track, degrees clockwise from north),
`aircraft_category`, and `aircraft` measurement metadata when retained. The map
draws every class OpenSky reports that also has a valid position and track as
yellow aircraft symbols; the Countries-panel selector narrows that set in the
browser. `aircraft_category` is OpenSky's own weight and role classification of
state vector index 17, not the ICAO ADS-B emitter category: 0 is no information,
1 is no emitter category, 2 Light (<15,500 lb), 3 Small (15,500-75,000 lb), 4 Large
(75,000-300,000 lb), 5 High Vortex Large (such as B-757), 6 Heavy (>300,000 lb),
7 High Performance, 8 Rotorcraft, 9 Glider/sailplane, 10 Lighter-than-air,
11 Parachutist/skydiver, 12 Ultralight/hang-glider/paraglider, 13 Reserved,
14 Unmanned Aerial Vehicle, 15 Space/trans-atmospheric, 16-17 surface vehicles
and 18-20 obstacles. Values above 20 are dropped. None of this is a military
classification; the Military selector uses the separate aircraft registry flag.
See [SOCIAL_MILITARY.md](SOCIAL_MILITARY.md) for
coverage and live-access limits.

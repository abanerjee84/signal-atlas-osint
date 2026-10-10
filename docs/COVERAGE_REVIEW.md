# Dashboard coverage review

Checked 10 October 2026. The screenshot exposed two defects: sidebar counts described the loaded page instead of all matching records, and aircraft/thermal collectors used a South Asia box even when the interface selected all countries. Both are fixed. The refreshed local dashboard displays observations across the Americas, Europe, Africa and Asia.

## What changed

- Layer counts use all retained records matching the selected period, search and geographic filters. Turning a layer off hides its records without changing its coverage count.
- The initial 500-record page alternates categories and occupied 30-degree geographic cells. Frequent aircraft snapshots no longer displace every other layer. Load more extends the selection; the feed is labeled as records by layer rather than a strictly chronological list.
- OpenSky and NASA FIRMS request worldwide data by default. Each collector samples geographic cells within its 1,000-record storage bound. The interface discloses worldwide sampling and records outside the bound.
- Mixed map clusters use a neutral color. Single-category clusters use that category's color, with counts by category in the hover details.
- Empty layers distinguish missing feed access, unavailable sources and no records in the selected period. Aircraft records are labeled position snapshots; military records are public announcements.

## Why some categories remain empty

| Category/source | Observed result | Meaning |
| --- | --- | --- |
| Cyber | Zero in 24 hours; six in seven days | CISA catalog additions predate the last-day window. These are vulnerability records, with no invented incident locations. |
| Economic | Zero in 24 hours; seven in seven days | ECB publication dates fall outside the last-day window. These are statements, not live commodity or currency prices. |
| Maritime | No configured feed | A licensed AIS provider and permitted display/history access are required. |
| ACLED | OAuth succeeds; data HTTP 403 | Account authentication does not establish event-data permission. Institutional registration or provider approval is still required. |
| ReliefWeb | Access required | Provider-approved app name remains pending at the user's request. |
| GDELT | Non-JSON worker response; independent check HTTP 429 | News discovery remains unavailable. BBC headlines continue to work, with limited coverage. |
| NATO | HTTP 404 | Legacy feed is unavailable. UK MOD announcements continue to work. |

The API snapshot at 11:23 UTC contained 3,681 matching last-day observations. Its first 500 records included 234 aviation, 233 environmental, 29 geopolitical and four military records. Those are display counts; the full counts were 2,266 aviation, 1,382 environmental, 29 geopolitical and four military. Data and rolling time windows continue to change.

## Worldwide collection is sampled

The verified OpenSky request fetched 8,291 states, accepted 962 and rejected 38 selected records that failed normalization; 7,291 records were outside the storage bound. FIRMS fetched 19,507 detections and accepted 1,000, with 18,507 outside the bound. Accepted records can update existing reports rather than create new database entries.

The newly ingested reports within these collection runs included aircraft positions in 62 countries, from longitude -168.4 to 179.7, and thermal detections in 44 countries, from -175.2 to 179.6. This establishes a broad geographic spread, not complete global coverage. ADS-B receiver gaps, sensor coverage, storage bounds, missing coordinates and unavailable sources still constrain the map. Repeated aircraft snapshots are separate observations; totals are not unique-aircraft counts.

The [OpenSky REST documentation](https://openskynetwork.github.io/opensky-api/rest.html) permits all-network state requests by omitting the geographic bounds. [NASA FIRMS area documentation](https://firms.modaps.eosdis.nasa.gov/api/area/) supports the `world` area. Both are now reflected in configuration and source metadata.

## “Edge connects”

No retained event title or description contains `EdgeConnect`; no title contains `edge`. The phrase needs clarification before assigning a cause. Code inspection found that frontend requests use the local `/api` and local country geometry. Provider acquisition happens on the backend. The map does not request third-party tiles. A browser-console error originated from an installed extension, not the dashboard bundle; this alone does not establish what browser network activity the user saw.

## Verification

All 59 backend tests passed. Regression cases cover complete layer counts, mixed-category pages, geographic sampling, worldwide provider requests and nullable aircraft callsigns. Python lint, frontend formatting and production build passed.

Browser checks verified the rendered world map, seven-day cyber/economic counts, hiding aviation without changing its count, loading 1,000 records without shrinking totals and restoration of the 24-hour view. Provider failures remain visible. Machine-readable evidence is in `coverage-verification.json`; the updated screenshot is `dashboard-coverage-fixed.jpg`.

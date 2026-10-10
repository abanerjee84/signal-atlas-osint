# Current codebase status — 10 October 2026

Reviewed against `BUILD_CONTRACT.md`, the current files, isolated regression probes and the running application. Live status was sampled at 22:36 IST (17:06 UTC); UI verification followed at 22:40 IST. This is a status review, not a claim that the remaining production acceptance criteria have been met. Application source files were not edited during this review.

The project is a working local research dashboard with substantially expanded collection and map analysis. Its foundation, source provenance, filtering and protected AI path are implemented. Recent aircraft and regional-analysis additions have defects that prevent calling the whole application production-ready. This directory has no Git repository, so an exact commit-based comparison with the previous session is unavailable.

| Current check                  | Result                                                                                       |
| ------------------------------ | -------------------------------------------------------------------------------------------- |
| Backend unit/integration suite | 76 passed in 4.86 seconds; one existing Starlette/HTTPX test-client deprecation warning      |
| Geographic connection tests    | 2 passed                                                                                     |
| Production frontend build      | Passed; main bundle approximately 1.108 MB minified / 301 KB gzip, with a chunk-size warning |
| Python dependency consistency  | Passed                                                                                       |
| Python lint                    | Failed: two unused imports and two repeated dictionary keys in the new NCSC/OFAC files       |
| Python formatting              | Failed: NCSC, OFAC, vendor geography and main API files                                      |
| Frontend formatting            | Failed: index.html                                                                           |
| Current manual browser check   | Dashboard and Military briefing render at port 5173; no captured application console errors  |
| Automated browser suite        | Present, but not rerun during this review; earlier results are historical evidence           |
| API and worker                 | Healthy API response and recent worker heartbeat                                             |
| Database                       | Schema version 3; approximately 84 MiB including WAL at the status sample                    |

Current implementation includes:

- Broad news collection, source-backed country connections, great-circle curves, wording-based connection colours and repeated map pulses. Animation and country co-mentions describe reporting relationships rather than verified movement.
- Military topic briefings, official/media labels, dated excerpts, map exploration and preparation of cited AI analysis. The sampled 24-hour view contained 47 defence-related reports: 23 official and 24 media across 11 feeds. Topics overlap.
- Reddit public discussion snapshots and manual browser capture, VADER scoring, comment/reply graphs, country-context heatmaps and explicit unknown-origin reporting. The sampled view had 160 unique Reddit records, 151 scored texts and 46 discussion links in the bounded graph. None supplied a supported author origin. YouTube remains an upload-wording dataset; X has no free collector connected.
- New NCSC advisories and OFAC sanctions guidance connectors, plus vendor-country context for CISA records. These are advisory/catalog/policy publications, not a complete real-time incident or market feed.
- New regional anomaly and cross-category overlays, evidence-weighted density and sentiment evidence cards.
- Migration 003 and storage/model fields for aircraft track, callsign and ADS-B category. Large-aircraft direction markers are present in frontend code.
- START.bat now launches Vite development serving at port 5173 with live reload and stops existing project services. The older README description of a build-and-preview launcher at port 4173 is stale. Port 4173 was not running during this check.

The live status sample showed 41 configured sources: 26 with successful status, 13 errors and two requiring access. There were 28,493 retained events, including 27,028 matching the sampled last-day window. Aircraft snapshots dominated that count; these are neither unique aircraft nor distinct world incidents. Cyber/economic records were absent from that 24-hour window despite working collectors, so their zeros do not establish collection failure.

The following findings should be addressed before further feature expansion:

1. **Regional anomaly results are unreliable.** `backend/analytics.py:127` binds its final time-window parameter before the filter parameters. Category, country, date and search filters can therefore return incorrect or empty results. The previous-period expression at line 123 counts records older than 12 hours inside the available baseline rather than the preceding six-hour interval. An isolated 20-record synthetic probe produced one unfiltered alert with a previous count of two, although the actual preceding-six-hour count was three; applying category and period filters to the same records removed the alert. Evidence is saved in `current-analysis-reproduction.json`. These fixtures existed only in a temporary database.

2. **The new aircraft direction markers lack their category input.** At the initial status sample, OpenSky reported `Collection failed (OperationalError)` and all 25,141 stored aircraft observations lacked track/category values. Its normal retry then succeeded at approximately 17:13 UTC without intervention: the database grew to 25,529 aircraft observations, with 388 populated tracks but zero populated categories. The immediate collection failure is therefore recovered; its original cause remains undiagnosed. The collector's request at `backend/connectors/opensky.py:42` omits `extended=1`, which the [official OpenSky REST documentation](https://openskynetwork.github.io/opensky-api/rest.html) requires to request category data. The glyph layer depends on that data and cannot match the current records. Map classes 4/5 also exclude the separately defined heavy category 6; the intended selection should be made explicit. The follow-up is recorded in `current-status-check.json`.

3. **NCSC attribution can incorrectly upgrade confidence.** `backend/connectors/ncsc.py:89` sets `Corroborated` from a country-name match in a single advisory. Its own evidence text says the claim is not verified responsibility. An isolated normalization probe confirmed this behaviour. `docs/ARCHITECTURE.md` requires independent cited sources and explicit analyst confirmation for that label. The current rule can overstate evidence, including in density weighting. OFAC's automatic `Verified` label also needs alignment with the documented verification policy.

4. **Layer health can misclassify stale sources as current.** `/api/status` computes staleness from last success. `/api/layers` instead reads raw database status rows and checks a `stale` field that does not exist in the persisted table. The timestamps must be evaluated consistently before aggregating layer health. This was found by code and schema inspection; the current source sample did not require injecting a stale row into the live database.

5. **Geographic context needs stricter precision labels.** The CISA vendor helper returns country centroids, but `backend/connectors/cisa.py:35` labels them `approximate` and calls them headquarters origin. These are country-level vendor context, not headquarters coordinates or exploitation locations. Unknown and distributed vendors need conservative treatment, with supporting mapping references. NCSC's first matching country word can likewise be context rather than explicit attribution; authoritative publication alone does not establish the claimed actor.

6. **Aircraft sampling disclosure undercounts omitted records.** OpenSky now caps each collection at 400, while `backend/worker.py:75` computes truncation against the general 1,000-record limit. The recorded pass fetched 12,270 states and stored 388 after 12 rejections; its 11,270 omission metric should account for the actual 400-record selection. The difference is 600 records. This affects coverage reporting, not the number of stored records.

GDELT remains rate-limited (429), ACLED data access returns 403, NATO's legacy feed returns 404 and Arctic Shift archive requests fail. Reddit feeds have mixed success and retain earlier valid snapshots until expiry. Maritime and ReliefWeb still require access configuration. These conditions are visible in `current-status-check.json`; they should not be confused with completed source integration.

Production acceptance still needs execution on the target 8 GB Ubuntu host: HTTPS and service validation, restart/outage recovery, sustained memory and disk measurements, a representative soak, and map animation performance. Semantic narrative clustering, multilingual sentiment calibration, representative opinion sampling, broad independent military corroboration, operational outage monitoring, live market coverage and individual analyst accounts remain gaps. The present country graphs and cross-category counts provide evidence navigation and collection co-occurrence, not causal intelligence.

The existing status/testing documents mix historical counts and older launcher behaviour. They should be reconciled after the defects above are repaired. The passing suite currently has no meaningful coverage of the new regional anomaly comparison, NCSC confidence rule, stale layer aggregation or end-to-end aircraft track persistence; test success alone does not validate those additions.

Review artifacts: `current-status-check.json`, `current-analysis-reproduction.json` and `current-codebase-dashboard.png`.

## Resolution in the following implementation turn

The six numbered findings above have been repaired and regression-tested. The original review is retained as point-in-time evidence. Current results and behavior are documented in `STATUS.md`, `TESTING.md`, `SOURCES.md` and `fixes-verification.json`. The user explicitly selected aviation categories 4 and 5; category 6 is excluded. The extended live collection produced 151 eligible reported tracks and the browser rendered 151 small yellow aircraft symbols. Retained CISA/NCSC records were reprocessed with conservative evidence/context labels. External provider gaps, production-host acceptance work and the bundle-size warning remain outside these code-defect fixes.

# Test results and reproducibility

## Public threat maps and country routes — 11 October 2026

The backend suite passed **194 tests**, including live-lease ownership/expiry regression coverage. Three additional status-publication tests passed for transient and permanent Windows reader locks and the disposable bridge fallback, bringing backend coverage to 197 tests. All **13 Node tests** passed, including heading bearings across the dateline and same-country detections retaining both endpoint roles without false arrows. The production build and Python lint passed. Runtime dependencies were unchanged.

The requested [webapp-testing workflow](https://github.com/anthropics/skills/tree/main/skills/webapp-testing) was applied with native Python Playwright against the existing app. Checks verified nine merged layer controls; cyber cards, routes, direction arrows and endpoints disappearing when disabled; the Countries attacker/victim view and provider filter; a selected route showing explicit A/origin and V/target text; source-linked detail evidence; and 100 public-discussion posts. There were no page errors. The seven-day cyber view displayed 201 combined cards, including 127 BunkerWeb detections. Its Countries table showed 32 BunkerWeb routes, including Germany → Germany; the world map rendered 96 static direction arrows and 27 endpoints. Screenshots of the routes table and selected route were visually inspected. Counts describe the sampled collection at verification time.

A final browser rerun after status freshness and responsive route framing changes passed with no page errors. It displayed 239 combined cyber cards, including 165 BunkerWeb detections; the provider table had 43 routes, with 117 rendered direction arrows and 30 endpoints. The selected-route screenshot was visually inspected again.

The explicitly authorized background gathering process fires every 120 seconds and opens no listening port. Consecutive recorded starts at 03:29:26, 03:31:26 and 03:33:26 UTC verified the interval. A persistent Windows delete-sharing lock was found on the disposable public status bridge; bounded atomic replacement retries and an explicit in-place fallback were added and tested. BunkerWeb supplied real samples for several targets, including Germany, Hungary, the Netherlands, France, Romania and the US. Bitdefender's public polling transport returned plain `ok` instead of a valid handshake, so source health reports failure and no Bitdefender samples are invented. Site transport, timestamps and coverage limits are documented in [THREAT_MAP_SCRAPERS.md](THREAT_MAP_SCRAPERS.md).

Neither server was started, stopped or restarted: API port 8000/PID 36744 and Vite port 5173/PID 26148 remained unchanged. The data-gathering process alone was reloaded to apply the Windows status-file fix. Historical sections below describe earlier verification.

## Public-source and Threat Actor update — 11 October 2026

The full backend suite passed **181 tests** after the new layer and social collectors were added. A final focused run passed **21 threat/social tests**, including two additional regressions for researcher-country separation and a phishing campaign's explicit target. All **nine Node tests**, Python lint/format checks and the production build passed. The existing Starlette test-client deprecation warning remains.

The requested [webapp-testing workflow](https://github.com/anthropics/skills/tree/main/skills/webapp-testing) was applied with native Python Playwright against the already-running application. No development server, production preview, server helper or resident worker was launched, stopped or restarted. Listening process identities stayed unchanged: API port 8000/PID 36744 and Vite port 5173/PID 26148.

Browser checks used real retained reports. They verified ten layer controls, removal of Threat Actor cards/edges when disabled, a persisted single-layer selection, seven-day filtering, independent threat counts, source-linked attribution details and the combined public-discussion dataset. The default 24-hour view displayed three threat reports and one edge. The seven-day view displayed **45 reports and two rendered edges**. The social panel displayed **100 source posts**. No page errors were captured. Screenshots of the world view, sentiment, public posts, isolated threats and threat detail were visually inspected. Counts describe this collection time, not guaranteed coverage.

One bounded public collection pass successfully stored eight research/threat feeds, eight additional geopolitical feeds, five Mastodon/Lemmy feeds and a public Telegram preview. The Reddit world-news feed returned 100 entries; other Reddit requests returned HTTP 429 and were left on backoff. Provider errors are not converted into neutral sentiment or invented observations. A missing Telegram robots file returned 404; correcting that handling allowed 13 timestamped public posts to be collected without bypassing denials or throttling.

The existing Python processes still hold the older registry. New data can be read by their existing generic endpoints, while full scheduled collection, platform-specific filtering and new source-health entries require the next user-controlled backend/worker reload. This reload was not performed.

For repeatable browser verification without server lifecycle actions, install the optional Python Playwright package and use an already available Chromium binary:

```powershell
.\.venv\Scripts\python.exe -m pip install playwright==1.63.0
.\.venv\Scripts\python.exe scripts\check_running_app.py --url http://127.0.0.1:5173 --chromium "C:\path\to\chrome.exe"
```

The script waits for completed refreshes, preserves request limits by loading a saved single-layer selection in one step, and writes local screenshots/results under ignored `data/run/public-update-browser`. It does not install a browser or invoke a server helper. The historical generic Playwright suite below may start servers and must not be used when server lifecycle changes are prohibited.

Verification date: 10 October 2026. Development host: Windows 11 build 22635, Python 3.12.14, Node 24.18.0, 16 logical CPUs, 68,640,628,736 bytes physical RAM. The deployment target remains an 8 GB Ubuntu server; this host is not that target.

## Automated verification

Current backend verification: 88 tests passed in 6.40 seconds after the status-review fixes. Four Node tests passed for connection geometry and aircraft selection/latest-position behavior. New regressions cover filtered regional windows and all three time bases, consistent stale-source health, conservative advisory confidence, country-centroid precision, retained-record repairs preserving analyst reviews, extended OpenSky requests, track persistence, class filtering before pagination and the actual collection bound. Tests cover both migrations and existing-schema upgrade, normalization, conservative deduplication, separate position observations, original reports, null coordinates, country and dateline filtering, time-basis ordering, literal search/SQL injection input, concurrent duplicates, job locks, rollback, retention, backup and restore. API tests exercise required endpoints and input/body/rate limits. Source tests cover access failure, secret-free error status, malformed records, provider failures, retry pacing, XML entities and location rules. AI tests use explicit mock transports for quotas, cache reuse, source citation validation, schema rejection, timeout, provider limits, zero-price policy, fallback and non-AI responsiveness during inference.

Historical browser suite: six tests passed in local Chromium during the earlier implementation. That suite was not rerun for the latest fixes; focused manual Chrome checks verified 151 yellow direction icons with real retained data, map rendering, details and no captured application console errors. They require rendered countries and observations rather than just a canvas element. They check source-linked details, session-persisted layer selection, country/time filters, playback, empty states, themes, collapsing panels, keyboard dialog dismissal/focus return, mobile overflow and controlled API failure. The production test renders the compiled bundle under the exact CSP from `deploy/nginx-headers.conf` and checks map workers and sentiment chart rendering.

Current production build, Python lint, Python/frontend formatting and `pip check` passed. The build still reports a main-bundle size warning (about 1.109 MB minified / 302 KB gzip). npm/Python audit results below are from the earlier verification; audits were not repeated for these source-only changes. The Starlette development test client emits one deprecation warning for its HTTPX transport; test assertions pass. No runtime dependency was changed away from the required HTTPX client to hide that warning.

The browser suite uses real retained local records for its happy path. Collect a public feed before running it on a clean machine. Mocked outage responses occur only inside a browser test and are labeled synthetic. Backend synthetic records stay in temporary test databases and never seed application intelligence.

Browser tests use unique documentation-range peer addresses through the trusted local proxy so repeated runs do not share a rate-limit counter. The rate-limit unit test checks the actual 120-request threshold. Production Nginx overwrites forwarded addresses with the real client peer.

```powershell
.\.venv\Scripts\python.exe -m backend.worker --once --source usgs
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check backend tests
npx prettier --check src index.html tests/browser vite.config.js playwright.config.js
npm run build
npx playwright install chromium
npm run preview
```

With the production preview running in another terminal:

```powershell
$env:OSINT_PRODUCTION_URL='http://127.0.0.1:4173'
npm test
.\.venv\Scripts\python.exe scripts\benchmark.py
node scripts\browser_benchmark.mjs
.\.venv\Scripts\python.exe scripts\audit.py
$env:NODE_OPTIONS='--use-system-ca'
npm audit
```

The Playwright configuration starts development servers when needed. `reuseExistingServer` is enabled outside CI. Review ports/processes if another application owns 8000, 5173 or 4173. The production-specific test skips unless its preview URL is configured. `scripts/browser_probe.mjs` prints browser worker/console failures and saves a diagnostic screenshot.

## Measurements

The backend benchmark generated 10,000 synthetic environment records in an isolated temporary SQLite WAL database, then deleted it. In-process ASGI HTTP, warm OS file cache, 60 filtered 500-event responses:

| Measurement                             | Result           |
| --------------------------------------- | ---------------- |
| Synthetic ingestion                     | 2.78 seconds     |
| Query median                            | 36.43 ms         |
| Query sample p95                        | 41.64 ms         |
| 20 concurrent 100-event requests, total | 225.41 ms        |
| Memory after ingestion                  | 68,771,840 bytes |
| Peak sampled during sequential polling  | 83,156,992 bytes |
| Memory after concurrent polling         | 89,858,048 bytes |
| Fixture database                        | 28,094,464 bytes |

These figures include no network/proxy latency and cover a short sample. They do not establish long-running leak absence or actual Ubuntu request latency. The requested target p95 below 500 ms must also be measured through the deployed serving path on representative data.

`browser-benchmark.json` records five fresh-context production loads under a stated CDP network profile: 10 Mbps down, 5 Mbps up, 50 ms latency and headless SwiftShader WebGL. Readiness requires rendered observations and the first API refresh to complete. It is an emulated local connection rather than actual broadband, and the Vite preview has no deployed Nginx gzip. The raw samples, maximum and median are the evidence; no sustained 30 FPS claim is made.

Live source checks, including errors and credential dependencies, are saved in `live-source-status.json`. Audits save complete point-in-time JSON reports. Raw source counts and timestamps are not invented or fixed in the interface.

## Outstanding operational verification

Nginx syntax, systemd units, actual certificate issuance/renewal, service restart, target network outage recovery, target disk forecast and representative 24-hour memory/ingestion soak remain to be run on the actual Ubuntu host. Credentialed feed tests and a live OpenRouter completion remain access-dependent. The acceptance checklist is in `DEPLOYMENT.md`.

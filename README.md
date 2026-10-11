# Signal Atlas OSINT

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12%2B-3776AB.svg)](requirements.txt)
[![Node.js 22.12+](https://img.shields.io/badge/Node.js-22.12%2B-339933.svg)](package.json)

**A global intelligence map and investigation workspace for following public reports, comparing narratives, and tracing relationships back to their sources.**

Signal Atlas brings geopolitical news, defence reporting, aircraft positions, cyber advisories, economic developments and environmental observations into one dashboard. Follow a report from its map marker to the original publication, compare country mentions and sentiment, or preserve evidence in an investigation case.

![World map with intelligence layers, country rankings, source connections and aircraft cards](docs/aircraft-cards-coverage.png)

_Example from a collected dataset. A fresh installation starts empty and fills as enabled sources succeed. Screenshots show coverage at capture time._

## What you can do

- **Explore the world map:** distinct layer symbols, heading-oriented yellow aircraft icons, clusters, density overlays, country filters and animated source connections.
- **Follow geopolitical and military reporting:** nine public Liveuamap regional maps, 18 additional publisher feeds, dated ISW assessments and existing worldwide/official reporting. Conflict symbols distinguish drones, missiles, airstrikes, artillery, bombs, sirens, deployments and other report types. Hover summaries show source wording, location, date and confidence; cards retain original citations.
- **Compare countries:** a map-side leaderboard for report mentions, sampled sentiment and intelligence activity, with source and sample counts.
- **Track eligible aircraft:** OpenSky classes 4 and 5, normally refreshed every two minutes, with short transitions between reported positions. Cards show registration country, altitude, speed, ground track and observation age.
- **Follow satellites and ISS:** 15 named spacecraft from public CelesTrak and AMSAT orbital files. Distinct satellite and ISS icons show calculated ground positions, with hover details, altitude, speed, mission, period and source elements. Positions update locally every two seconds; no account or key is needed.
- **Find layers by topic:** search above Display Overlays expands related concepts such as planes, hacking, oil prices and space station. It searches layer meanings locally and preserves your selected overlays.
- **Study public narratives:** English lexical sentiment, topic groups, regional comparisons and separate news, public-discussion and official-statement datasets.
- **Investigate cyber intelligence:** advisories, vulnerabilities, routing and outage observations, plus threat-actor, malware and technique relationships from reference catalogs.
- **Follow cyber threats:** the merged Cyber: Threat Actors layer combines attack reporting with Bitdefender ATTACK rows, BunkerWeb traffic, Imperva daily request aggregates and Radware's public map. Filter specific attack vectors separately from reputation blocks. Public Unit 42, Securelist and Mandiant article scrapers add technique evidence and CVEs. Radware's global method breakdown is displayed separately from country routes. Infrastructure geography remains separate from human attribution.
- **Collect public discussion without social API keys:** Reddit, Mastodon and Lemmy feeds plus timestamped public Telegram previews flow into the sentiment heatmap. Author origins remain unknown unless explicitly declared; country mentions describe discussion context.
- **Build a case:** indexed search, entity graphs, private notes, immutable evidence snapshots, media/document imports, chronological review and JSON/Markdown exports.
- **Use optional AI analysis:** OpenRouter summaries with source references, caching and local request budgets. Unstructured model output appears as a labelled draft; schema-valid output must pass citation-ID checks.

The nine selectable map layers are **Geopolitical events**, **Military OSINT**, **Aviation**, **Maritime**, **Global sentiment**, **Cyber: Threat Actors**, **Economic and energy**, **Environment and humanitarian**, and **Satellites & ISS**. The cyber switch combines advisories, investigations, attack reporting and sampled provider traffic. Layer availability depends on source access and the selected period.

**Reporting signals & alerts** shows regional surges in collected reporting and countries with reports across multiple enabled layers. Use the **Signals** button at the top of the map; it is separate from Intelligence layers. Alerts include comparisons and inspection actions; they are separate from optional AI analysis and do not establish escalation or causation. See [conflict collection and reporting signals](docs/CONFLICT_REPORTING.md). A centered map indicator shows progress for user-triggered computation, including filters and analysis. Routine dashboard refresh and live position updates stay quiet.

<details>
<summary>Preview conflict reporting and signals</summary>

![Conflict workspace with report-type symbols and inspectable reporting signals](docs/conflict-workspace.jpg)

</details>

<details>
<summary>Preview the threat-actor workspace</summary>

![Cyber workspace with compact controls, origin-to-target routes, provider attack types and reporting periods](docs/threat-actor-workspace.jpg)

Catalog relationships describe published reference knowledge. A name match or shared mention does not establish responsibility for an incident.

</details>

<details>
<summary>Preview the satellite workspace</summary>

![Satellite and ISS positions with altitude, mission, source elements and topic search](docs/satellite-workspace.jpg)

Positions are SGP4 estimates from public orbital elements, rather than live spacecraft telemetry. Polar ground positions can fall outside the world overview. Satellite history is not retained. See [orbital collection and accuracy](docs/SATELLITES.md).

</details>

## Run locally

Requires **Python 3.12+**, **Node.js 22.12+** (Node 24 also works), npm and Git. Internet access is needed to collect feeds; the map boundaries are bundled locally. No GPU or local language model is required.

### Windows

Run these commands in PowerShell:

```powershell
git clone https://github.com/abanerjee84/signal-atlas-osint.git
cd signal-atlas-osint
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
npm ci
Copy-Item .env.example .env
.\START.bat
```

`START.bat` stops this checkout's previous services, starts the API, collector and frontend, then opens [the dashboard](http://127.0.0.1:5173/). Keep its window open; press Enter there to stop all three services. Run it again after changing `.env`. Logs are written to `data/logs/`. It reports missing dependencies or ports occupied by another application. Windows administrator elevation is not required.

### Linux / macOS

```bash
git clone https://github.com/abanerjee84/signal-atlas-osint.git
cd signal-atlas-osint
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci
cp .env.example .env
```

Start each service in its own terminal, from the project directory:

```bash
# Terminal 1: API
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

```bash
# Terminal 2: source collector
.venv/bin/python -m backend.worker
```

```bash
# Terminal 3: dashboard
npm run dev
```

Open [the dashboard](http://127.0.0.1:5173/), [the investigation workspace](http://127.0.0.1:5173/advanced.html), or [the API reference](http://127.0.0.1:8000/api/docs).

For a single collection pass, use `python -m backend.worker --once` with the virtual environment's Python executable. Add `--source usgs` to collect only that provider.

## Sources and configuration

The public-feed dashboard works without social-media API keys. Copy `.env.example` to `.env` once during setup, then edit the local file. Provider credentials stay on the backend. `.env`, databases, evidence, logs and backups are excluded from Git.

The default registry contains [66 RSS/Atom feeds](docs/RSS_FEEDS.md), plus other public collectors. Source availability is shown separately from event counts. See the [threat and social collection notes](docs/THREAT_ACTIVITY.md) for attribution rules, vendor live-map references and limits.

| Coverage                     | Example sources                                                                                                       | Access                                                                                                                   |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Geopolitical news            | BBC regional feeds, Al Jazeera, DW, France 24, UN News, Africanews, MercoPress, CNA, RFI, ABC, Euronews, The Guardian | Public feeds; availability and publisher terms apply                                                                     |
| Military reporting           | UK Ministry of Defence, DVIDS, selected news reports                                                                  | Public announcements and reporting                                                                                       |
| Economic and energy          | BBC Business, Guardian Business/Energy, CNA Business, US EIA, ECB, OFAC                                               | Public feeds and releases                                                                                                |
| Cyber and threat references  | CISA, NCSC, SANS, MITRE ATT&CK, MISP galaxies, Malpedia, ETDA                                                         | Public feeds/catalogs; source-specific reuse terms                                                                       |
| Published attack reports     | BleepingComputer, SecurityWeek, The Hacker News, The Record, Cybersecurity Dive, ESET, Microsoft, Cisco Talos         | Public RSS; unverified excerpt attribution, not live packet telemetry                                                    |
| Sampled cyber detections     | Bitdefender ATTACK table, BunkerWeb blocked-request stream, Imperva daily country-pair dataset                        | No keys. Ten-second live-feed checks; Imperva has a dated daily period and a separate 15-minute check.                   |
| Public narratives            | Reddit feeds/archive deliveries and browser imports, Mastodon, Lemmy, public Telegram previews; YouTube channel feeds | No social API keys; selected samples. YouTube uploads are separate from comments. X has no automatic collector connected |
| Environment and humanitarian | USGS, NASA FIRMS, ReliefWeb                                                                                           | USGS is keyless; FIRMS needs a map key; ReliefWeb needs an approved app name                                             |
| Aviation                     | OpenSky state vectors                                                                                                 | Account client credentials and provider credits                                                                          |
| Conflict events              | ACLED                                                                                                                 | Account credentials **and** API entitlement                                                                              |
| Maritime                     | Administrator-configured normalized AIS feed                                                                          | Authorized feed URL and any required credentials                                                                         |
| AI assessment                | OpenRouter                                                                                                            | Optional API key; free-only mode enabled by default                                                                      |

See [source configuration](docs/SOURCES.md) and the in-app source status for schedules, coverage, failures and permission requirements. Historical verification documents describe past checks; they do not guarantee that a provider is available today.

To enable protected analysis, imports and private investigations, set a strong random `OSINT_ADMIN_TOKEN` in `.env`, restart the services, and enter that token in dashboard **Settings** or the investigation workspace's connection form. This is an application access token, separate from Windows privileges and provider keys. The browser holds it in tab memory until reload. Keep `OSINT_ADVANCED_PUBLIC_READ=false` for private investigation records.

Optional settings include `OSINT_OPENSKY_POLL_SECONDS` (120 to 1800), retention periods, collection bounds, approved outbound hosts and additional RSS definitions. AI defaults to `OSINT_AI_FREE_ONLY=true`; local budgets count requests, not currency, and provider quotas still apply.

## Reading the map correctly

Reported coordinates, country context and publisher origin have different meanings. A country mentioned in a headline is regional context, not a confirmed incident location. Map edges can indicate publisher-to-context links, co-mentions or documented reference relationships; inspect their source and basis before interpreting them.

Cyber traffic routes are blue; reported attacker-to-victim attribution links are pink. An infrastructure country never establishes the attacker's nationality. Vendor samples are shown separately from published reports and are not global attack totals. Natural Earth reference points supplement countries omitted by the low-detail boundary file, without creating boundary polygons. See [the scraper analysis](docs/THREAT_MAP_SCRAPERS.md).

With **Cyber: Threat Actors** active, the Countries ribbon offers an **Attacker → Victim** table with provider filters. Small A/V markers, moving arrows, a top legend and hover evidence identify origins, targets and source reports. A separate gathering thread checks live feeds every ten seconds against the running database, without opening a server port: `python -m scripts.collect_threat_maps --watch`. Install the optional pinned `requirements-browser.txt` renderer and Chromium for the Bitdefender table and normal Imperva page. Imperva rows preserve their daily period and request counts; choose **Last 7 days** for older reports. Arrows illustrate direction rather than packet timing. See [collection details and graceful gatherer shutdown](docs/THREAT_MAP_SCRAPERS.md). Provider backoff still applies.

Route rows, hover previews and selected routes show **Vector / type** using the provider's category or blocking reason. Generic Bitdefender ATTACK rows remain **Not specified by provider**; they do not establish a technique. The compact toolbar keeps overlay switches in **Layers** and explanations in **Key**. World view fits the canvas beside the Countries ribbon, excluding polar cartography above 74°N and below 57°S; collapsing the ribbon refits the overview without resetting a selected route or a manual view.

Sentiment describes the wording of sampled English text. It does not measure national opinion, verify a claim or identify a person's stance. Unknown origins stay unknown. Non-English reports remain available without an English sentiment score.

Aircraft positions are a bounded geographic sample of eligible OpenSky classes, with network coverage gaps and source timestamps. Ground track is movement direction, not necessarily nose heading. Registration country is not departure origin; departure and destination airports are unavailable from state vectors. Animation interpolates between observations without extrapolating a future route.

Collection success and citation validation do not establish truth. AI drafts are labelled as unvalidated, and structured citation checks confirm that references belong to the evidence packet. Zero counts can mean no matching reports, an unavailable source or missing access; check source health and the time filter.

## How it is built

The frontend uses **vanilla JavaScript, Vite, MapLibre GL and ECharts**. **FastAPI** serves a **SQLite WAL** database with FTS5 search. A separate Python worker normalizes feeds, records provenance and schedules collection. Optional OpenRouter requests run on the server.

```text
backend/       API, collectors, analysis, investigation modules and migrations
src/           Map, timeline, feeds, country rankings and investigation UI
public/        Local country boundaries, map attribution and favicon
scripts/       Launcher, maintenance, backups, audits and verification tools
deploy/        Ubuntu systemd services, timers and Nginx configuration
tests/         Backend, Node and browser tests
docs/          Architecture, source notes, operations and verification records
```

The original [build contract](BUILD_CONTRACT.md) and [advanced integration specification](ADVANCED_OSINT_SPEC.md) describe the project requirements. The main API uses `/api/`; investigation modules use `/api/v1/`.

## Development and checks

Using the Windows virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check backend tests
node --test tests/aircraft.test.mjs tests/geo-lines.test.mjs
npm run build
npx playwright install chromium
npm test
```

On Linux/macOS, substitute `.venv/bin/python`. Browser tests start or reuse the local API and frontend. Synthetic test fixtures are confined to temporary databases; the application contains no seeded intelligence. Dependency audits can be run with `python scripts/audit.py` using the virtual environment and `npm audit`.

## Documentation and deployment

- [Architecture and evidence rules](docs/ARCHITECTURE.md)
- [Map symbols, connections and country rankings](docs/MAP_INTERFACE.md)
- [Investigation workspace](docs/ADVANCED_OSINT.md)
- [Threat intelligence sources and relationships](docs/THREAT_INTELLIGENCE.md)
- [Social narratives and military reporting](docs/SOCIAL_MILITARY.md)
- [Conflict collection, symbols and reporting signals](docs/CONFLICT_REPORTING.md)
- [Conflict tracker and upstream publisher audit](docs/CONFLICT_SOURCE_AUDIT.md)
- [Aircraft refresh, card metadata and AI drafts](docs/AIRCRAFT_ECONOMIC_AI_UPDATE.md)
- [API guide](docs/API.md)
- [Operations, backups and recovery](docs/OPERATIONS.md)
- [Ubuntu deployment](docs/DEPLOYMENT.md)
- [Testing and recorded measurements](docs/TESTING.md)
- [Configured RSS and Atom directory](docs/RSS_FEEDS.md)
- [Threat attribution, live-map review and public social collection](docs/THREAT_ACTIVITY.md)
- [Implementation status and remaining acceptance work](docs/STATUS.md)

The Windows launcher is for local development. Ubuntu deployment includes systemd services, backup/monitoring timers and an Nginx HTTPS configuration. Acceptance testing on the intended production host remains necessary. Private investigations currently use a single administrator principal; multi-user accounts and roles are not implemented.

Contributions are welcome through issues and pull requests. For a new connector, document its access requirements, terms, timestamp semantics and geographic precision, and test normalization and failure handling. Never include provider credentials or private evidence in a contribution.

## License

Project code is licensed under the [MIT License](LICENSE), copyright 2026 Abhijit Banerjee.

Third-party dependencies, provider content and reference data retain their own licenses and terms. Natural Earth country boundaries are public domain; see [map attribution](public/MAP_LICENSE.txt). MITRE ATT&CK material retains [MITRE's license and notice](docs/licenses/MITRE-ATTACK.txt). The project license does not grant redistribution rights to collected news, social posts, aircraft data or other provider content.

# Public threat-map collection

Verified on 11 October 2026 against the existing application. Collection requires no keys and opens no server port.

## Specific attack methods

The Countries ribbon offers **Known attack vectors only**, individual technique filters, and a separate **Reputation / blocking signals** view. Known methods appear first in the route list. SQL injection, XSS, RCE/RFI, path traversal, phishing, credential attacks and named flood methods are matched against explicit provider labels or primary article wording. Each report retains a short evidence excerpt and any named CVEs. Extraction uses a shared deterministic vocabulary; no LLM response is required.

BLACKLIST and DNSBL are reputation decisions. Ransomware and a breach describe activity or outcomes. Generic ATTACK, botnet, web attack and DDoS without a subtype do not establish a specific method. These labels remain visible as source activity but are excluded from the known-vector view. A detection does not by itself establish a successful compromise.

[Radware](https://livethreatmap.radware.com/) is scraped through its normally rendered public page. The scraper observes the map sample delivered to that page and reads the visible **Top network attack vectors** and **Top application violations** tables. No direct Radware API client, credential, cookie export or injected request is used. The map sample contains source country, destination country, broad category and timestamp. Missing destinations remain unknown and create no edge. The timestamp lacks a timezone suffix; receipt time supplies the timeline fallback.

Radware's detailed TCP/IP/UDP/HTTPS flood and application-violation percentages describe a separate global statistics period. The feed panel displays that period, scrape age and source link. **Those percentages are never assigned to country pairs.** The breakdown remains global when the map is filtered. Stale snapshots are marked after two minutes.

Three additional scrapers discover articles through publisher feeds and then read public HTML: [Unit 42](https://unit42.paloaltonetworks.com/), [Securelist](https://securelist.com/) and [Google / Mandiant](https://cloud.google.com/blog/topics/threat-intelligence). Each checks at most eight same-host articles every 15 minutes, within 45 days of publication. Only records with attack context and explicit technique wording are accepted. Full article bodies are processed in memory; stored excerpts and technique evidence are bounded. Country roles are unverified textual extraction, never inferred from publisher location or actor aliases. Use **Last 30 days** for older research.

All sources use normal public delivery and respect robots exclusions and provider denials. Failures appear in source health. The scraper does not bypass access controls or manufacture a method to fill an unknown field.

| Provider                                                    | Collection                                                                                                                                                                                                                                                                                                              | Timing and meaning                                                                                                                                                                                                                                                                          |
| ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Bitdefender](https://threatmap.bitdefender.com/)           | Python Playwright keeps the normal public page open and reads its five-column bottom table. Only **ATTACK** rows are accepted, with origin and target from the country columns. INFECTION, SPAM, N/A targets and unsupported countries are excluded.                                                                    | Read every 10 seconds. Stable row hashes deduplicate unchanged table snapshots. The displayed time omits the year, so occurrence remains unknown.                                                                                                                                           |
| [BunkerWeb](https://www.bunkerweb.io/threatmap/)            | HTTPX reads the public SSE transport at `threatmap.bunkerweb.io/stream`. Origin, target, reason and provider time are retained.                                                                                                                                                                                         | Four-second bounded samples every 10 seconds. Events outside each window are missed. Its time-of-day text has no established date/timezone; receipt is the timeline fallback.                                                                                                               |
| [Imperva](https://www.imperva.com/cyber-threat-attack-map/) | The normal page loads public compressed CSV under `/public/threat-map-data-v2/day=YYYY-MM-DD/data/HOUR.gz`. The optional renderer observes that response. Columns match the table: source, target, industry, category, attack, client, requests and hour. HTTPX remains available where ordinary public downloads work. | Checked every 15 minutes because its reporting period is daily. At most 100 rows are sampled round-robin across country pairs. Request counts are not distinct attacks. The reporting-period end controls publication/date filters: select Last 7 days to see datasets older than 24 hours. |

The direct Bitdefender polling transport returned an invalid handshake; its legacy HTTP adapter reports that failure. Imperva returned a 200 HTML “Pardon Our Interruption” page to the research HTTP client. Its normal rendered page loaded a public dataset successfully. No user-agent impersonation, cookie copying, CAPTCHA solving or challenge bypass is used. If normal page delivery fails, collection remains blocked and appears in source health.

## Gathering thread

The database must already be initialized. Install the optional renderer deliberately:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-browser.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m scripts.collect_threat_maps --watch
```

An installed Chromium may be supplied with `--chromium "absolute-path-to-chrome"`. `--no-browser` uses legacy HTTP transports only and cannot collect Radware. Playwright is a pinned optional dependency because these pages are generated by JavaScript; core server requirements are unchanged. One browser keeps the Bitdefender, Imperva and Radware pages open. The gatherer does not install a startup task or survive a machine restart automatically.

A single sequential thread fires every **10 seconds**, measured from each cycle's start. Initial page loads or slow networks can delay a cycle; overlapping jobs never launch. A 30-second cycle ceiling bounds stalled sources and shutdown. Persisted backoff applies independently, including Imperva's 900-second deadline. Robots policies are cached for ten minutes and evaluated for each destination.

An independent bounded article task shares the same gathering process and checks research deadlines once per minute. The articles themselves are fetched at 15-minute intervals; a 90-second ceiling prevents that task from delaying the map lane. No extra server or listening socket is created.

To stop only this gathering process gracefully, create `data/run/threat-map-thread.stop`. It finishes or cancels bounded collection, closes its browser, marks its heartbeat stopped and releases its renewable database lease. A new gathering process clears the stop file after obtaining that lease. This mechanism never starts, stops or restarts application servers.

The ignored heartbeat is `data/run/threat-map-thread.json`. Older running APIs use the ignored aggregate health bridge `public/threatmap-status.json`; it contains status and counts, not private posts, IPs or credentials. Atomic status replacement retries Windows reader locks. Only the disposable public bridge permits an in-place fallback; the UI tolerates a partial JSON read.

## Evidence and map behavior

Traffic origin describes infrastructure geography, never human identity or nationality. Records retain `actor="Unknown actor"` and separate traffic-origin/target fields. Published actor attribution is another evidence class. Country centers are illustrative; the Natural Earth [supplement](../public/country-context.geojson) includes small countries absent from the bundled polygons.

The top legend uses amber **A** for origin, cyan **V** for target and cyan arrows for observed traffic. Magenta identifies published attribution; gold highlights a selected route. These colors distinguish roles and evidence, not severity or sentiment. Small icons show source titles, country roles, counts, last-seen time and daily periods on hover. Clicking opens evidence. The Countries ribbon supplies equivalent routes and provider filters for keyboard users.

Every displayed non-domestic route has arrows replaying over six seconds. Animation illustrates **direction**, not packet timing or newly occurring attacks. Same-country detections retain both endpoint roles without inventing a cross-country path. Motion is throttled and paused for hidden/offscreen maps and reduced-motion preferences. The dashboard refreshes telemetry every ten seconds without rerunning its entire query.

Only whitelisted geography, type, timing, aggregate request counts, industry and client type are stored. IPs, attacked-resource URLs, cookies and arbitrary payloads are discarded. Imperva input is capped at 1 MiB compressed and 8 MiB expanded. Each provider retains at most 2,000 observations and seven days, independently of published reports. Repeated snapshots are deduplicated, but provider rows do not establish unique incidents or worldwide totals. Coverage and provider terms still apply.

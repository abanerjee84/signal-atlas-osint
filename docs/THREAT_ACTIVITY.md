# Threat reports, live maps and public discourse

The **Cyber: Threat Actors** layer combines cyber advisories, investigations, recent attack reporting and sampled provider detections behind one switch. TA shield markers distinguish attack reports and detections within the shared layer; CY marks identify advisory/context records. Country rankings and the timeline count this as one layer. The underlying `cyber` and `threat` record categories retain their evidence types for API compatibility.

## How an edge is established

The collector reads a publisher's feed title and bounded excerpt. Deterministic rules identify explicitly attributed attacker countries and countries described as targets. An edge requires both roles in the source wording. The detail card keeps the extraction basis and original publication link. Actor names alone, publisher geography, country co-mentions and infrastructure IP locations do not create attacker-country attribution.

For example, “Chinese hackers target Japan” supports a **reported** CN → JP relationship. “Lazarus malware found by researchers in Germany” supplies neither an attacker country nor an explicitly targeted country. Unknown and ambiguous origins remain unknown; reports still appear in the feed. This conservative extraction can miss valid attribution and can misread complex wording. It is unverified reporting, not a finding that an attack succeeded.

Connections use illustrative country centers, move from origin to target and open source-linked details. They obey selected time, country, text and viewport filters. Historical playback removes connections whose reports or observations have not yet appeared. Separate queries preserve up to 500 published reports and 300 sampled provider detections in the selected period, so high-volume telemetry cannot bury reporting. Identical published URLs do not add another report to an edge. Detections count by collection observation ID because a vendor map uses the same URL for multiple observations. Feed publication and observation receipt are distinct from attack occurrence time.

Pink links show reported attribution. Blue links show **observed traffic origin → destination**; an infrastructure location does not identify an actor, and blocked requests do not prove compromise. Single-location infection/spam detections have a point without an invented target edge. Unknown actor and country fields remain unknown.

The Countries ribbon offers an **Attacker → Victim** view only while the cyber layer is active. It lists full country names and ISO codes, counts and provider filters. Same-country detections remain in the table rather than disappearing or acquiring an invented cross-country line. Clicking a row highlights its route and opens an explicit origin/target card with source evidence. Persistent arrowheads and moving arrows face the target; orange **A** and blue **V** markers distinguish endpoint roles even with reduced motion enabled. These letters follow the providers' country labels and do not identify a human attacker.

## Sources and live-map review

Eight default research/news feeds refresh every 15 minutes: BleepingComputer, SecurityWeek, The Hacker News, The Record, Cybersecurity Dive, ESET WeLiveSecurity, Microsoft Security and Cisco Talos. The complete configured feed list is in [RSS_FEEDS.md](RSS_FEEDS.md).

The [awesome-osint Live Cyber Threat Maps section](https://github.com/jivoi/awesome-osint#live-cyber-threat-maps) was reviewed as a discovery list, not a license to copy each service's telemetry. Selected resources appear in the shared cyber feed's expandable source panel:

| Resource                                                                                                      | What it supplies                                                        | Integration                                                                                                                                                                       |
| ------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Cisco Talos](https://talosintelligence.com/)                                                                 | Published campaign research and threat intelligence                     | Its linked [public research RSS](https://blog.talosintelligence.com/rss/) is collected. Named UAT campaign identifiers are recognized; attribution still requires source wording. |
| [NETSCOUT Horizon](https://www.netscout.com/ddos-attack-map)                                                  | Provider DDoS observations and an interactive map                       | External reference. Traffic source locations do not establish actor nationality.                                                                                                  |
| [Kaspersky Cybermap](https://cybermap.kaspersky.com/subsystems)                                               | Antivirus, web/mail protection, intrusion and other security detections | External reference. Its [map terms](https://cybermap.kaspersky.com/tos) restrict redistribution, so telemetry is not copied.                                                      |
| [BunkerWeb](https://www.bunkerweb.io/threatmap/) | Country pairs and blocking reasons | Public SSE collector connected after ordinary host requests returned 200. Earlier research-tool 403 responses did not reflect host access. |
| [Bitdefender](https://threatmap.bitdefender.com/) | Provider map channels for attacks, infections and spam | Python Socket.IO polling collector installed. The live transport returned plain `ok`, without a valid handshake, during review; source health reports failure and no events are invented. |
| [Check Point](https://threatmap.checkpoint.com/) and [FortiGuard](https://fortiguard.fortinet.com/threat-map) | Vendor threat-map/alert resources                                       | Map requests returned HTTP 403 during review; no scraper was connected.                                                                                                           |

No simulated attack stream is created. Animated edges illustrate the selected reports and collected traffic samples; animation does not assert packet arrival timing. Reference catalogs continue to provide background knowledge without automatically asserting responsibility for an incident. Transport analysis, sampling, retention and timestamp limitations are documented in [THREAT_MAP_SCRAPERS.md](THREAT_MAP_SCRAPERS.md).

## Public sentiment without social API keys

The public-discussion dataset combines existing Reddit feeds/archive deliveries with three Mastodon hashtag RSS feeds, two Lemmy community RSS feeds and public Telegram channel HTML previews. Default Telegram channel selection is a narrow, potentially biased publication sample; configure other permitted public channels using `OSINT_TELEGRAM_CHANNELS` in `.env`.

Collectors use no social credentials, login cookies or hidden endpoints. Telegram previews follow published robots restrictions; a missing robots file allows the public preview, while denied access, throttling and network errors stop collection. Only visible timestamped message text is extracted. Previous social snapshots are replaced on success and local public records expire after 24 hours. Reddit requests are bounded to 100 feed entries and respect collection backoff. See provider health for failures rather than interpreting an empty sample as neutral opinion.

English VADER scores the post/comment wording. Mastodon and Telegram text is scored once, without duplicating its derived title. Identical post IDs are deduplicated across feed deliveries. Unknown author locations remain unknown. A country's heatmap represents mentions in sampled wording; it is not national public opinion. Country co-mentions are context links, while comment-to-thread connections require an explicit relation. YouTube uploads remain a separate media dataset and contain no viewer comments. X has no working automatic public collector connected.

## Applying changes without touching running servers

The current change was checked against the existing application. No server was created, stopped or restarted. A bounded one-pass collection stored real public additions in the existing database, which the running API can already read. Frontend compatibility supports the new threat records through their evidence tags and combines the new platforms under **All connected platforms**.

The already-running Python service and worker keep their previously loaded code. The expanded registry, per-platform filters and full source-health entries take effect at the next user-controlled service/worker reload. This reload is not performed by the verification scripts. At the user's explicit request, a separate background data-gathering thread fires every two minutes for BunkerWeb and Bitdefender without opening a server port. It respects source deadlines and backoff. Each update writes an ignored, public aggregate `public/threatmap-status.json` so the current frontend can show both map collectors' results before that reload. The bridge contains no event payloads and ages samples as stale; the current backend's authoritative status takes precedence when available.

For an optional one-pass update against an already initialized database:

```powershell
.\.venv\Scripts\python.exe -m scripts.collect_public_updates --source threat_cisco_talos
.\.venv\Scripts\python.exe -m scripts.collect_public_updates --source bunkerweb_threatmap --source bitdefender_threatmap
```

The script respects persisted collection deadlines and locks. It exits after collection; it has no server lifecycle actions. See [TESTING.md](TESTING.md) for browser verification against an existing application.

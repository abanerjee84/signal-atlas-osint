# Threat reports, live maps and public discourse

The **Threat Actor** layer follows recent published cyberattack and campaign reports. It has its own TA shield marker and animated country connections. It is separate from Cyber intelligence's advisories, infrastructure observations and reference catalogs.

## How an edge is established

The collector reads a publisher's feed title and bounded excerpt. Deterministic rules identify explicitly attributed attacker countries and countries described as targets. An edge requires both roles in the source wording. The detail card keeps the extraction basis and original publication link. Actor names alone, publisher geography, country co-mentions and infrastructure IP locations do not create attacker-country attribution.

For example, “Chinese hackers target Japan” supports a **reported** CN → JP relationship. “Lazarus malware found by researchers in Germany” supplies neither an attacker country nor an explicitly targeted country. Unknown and ambiguous origins remain unknown; reports still appear in the feed. This conservative extraction can miss valid attribution and can misread complex wording. It is unverified reporting, not a finding that an attack succeeded.

Connections use illustrative country centers, move from reported origin to target and open the cited report. They obey selected time, country, text and viewport filters. Historical playback removes connections whose reports have not yet appeared. The threat view examines up to 500 recent reports in the selected period; counts and connections describe that bounded set. Identical URLs do not add another observation to an edge. Feed publication time is distinct from attack occurrence time.

## Sources and live-map review

Eight default research/news feeds refresh every 15 minutes: BleepingComputer, SecurityWeek, The Hacker News, The Record, Cybersecurity Dive, ESET WeLiveSecurity, Microsoft Security and Cisco Talos. The complete configured feed list is in [RSS_FEEDS.md](RSS_FEEDS.md).

The [awesome-osint Live Cyber Threat Maps section](https://github.com/jivoi/awesome-osint#live-cyber-threat-maps) was reviewed as a discovery list, not a license to copy each service's telemetry. Selected resources appear in the Threat Actor feed's expandable reference panel:

| Resource                                                                                                      | What it supplies                                                        | Integration                                                                                                                                                                       |
| ------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [Cisco Talos](https://talosintelligence.com/)                                                                 | Published campaign research and threat intelligence                     | Its linked [public research RSS](https://blog.talosintelligence.com/rss/) is collected. Named UAT campaign identifiers are recognized; attribution still requires source wording. |
| [NETSCOUT Horizon](https://www.netscout.com/ddos-attack-map)                                                  | Provider DDoS observations and an interactive map                       | External reference. Traffic source locations do not establish actor nationality.                                                                                                  |
| [Kaspersky Cybermap](https://cybermap.kaspersky.com/subsystems)                                               | Antivirus, web/mail protection, intrusion and other security detections | External reference. Its [map terms](https://cybermap.kaspersky.com/tos) restrict redistribution, so telemetry is not copied.                                                      |
| [BunkerWeb](https://www.bunkerweb.io/threatmap/)                                                              | Blocked web requests                                                    | External reference. The map returned HTTP 403 during review; no guarded endpoint is bypassed.                                                                                     |
| [Check Point](https://threatmap.checkpoint.com/) and [FortiGuard](https://fortiguard.fortinet.com/threat-map) | Vendor threat-map/alert resources                                       | Map requests returned HTTP 403 during review; no scraper was connected.                                                                                                           |

No simulated attack stream is created. Animated edges show published report relationships, not packets arriving in real time. Reference catalogs continue to provide background knowledge without automatically asserting responsibility for an incident.

## Public sentiment without social API keys

The public-discussion dataset combines existing Reddit feeds/archive deliveries with three Mastodon hashtag RSS feeds, two Lemmy community RSS feeds and public Telegram channel HTML previews. Default Telegram channel selection is a narrow, potentially biased publication sample; configure other permitted public channels using `OSINT_TELEGRAM_CHANNELS` in `.env`.

Collectors use no social credentials, login cookies or hidden endpoints. Telegram previews follow published robots restrictions; a missing robots file allows the public preview, while denied access, throttling and network errors stop collection. Only visible timestamped message text is extracted. Previous social snapshots are replaced on success and local public records expire after 24 hours. Reddit requests are bounded to 100 feed entries and respect collection backoff. See provider health for failures rather than interpreting an empty sample as neutral opinion.

English VADER scores the post/comment wording. Mastodon and Telegram text is scored once, without duplicating its derived title. Identical post IDs are deduplicated across feed deliveries. Unknown author locations remain unknown. A country's heatmap represents mentions in sampled wording; it is not national public opinion. Country co-mentions are context links, while comment-to-thread connections require an explicit relation. YouTube uploads remain a separate media dataset and contain no viewer comments. X has no working automatic public collector connected.

## Applying changes without touching running servers

The current change was checked against the existing application. No server was created, stopped or restarted. A bounded one-pass collection stored real public additions in the existing database, which the running API can already read. Frontend compatibility supports the new threat records through their evidence tags and combines the new platforms under **All connected platforms**.

The already-running Python service and worker keep their previously loaded code. The expanded registry, scheduled collectors, per-platform filters and full source-health entries take effect at the next user-controlled service/worker reload. This is deliberately not performed by the verification scripts.

For an optional one-pass update against an already initialized database:

```powershell
.\.venv\Scripts\python.exe -m scripts.collect_public_updates --source threat_cisco_talos
```

The script respects persisted collection deadlines and locks. It exits after collection; it has no server lifecycle actions. See [TESTING.md](TESTING.md) for browser verification against an existing application.

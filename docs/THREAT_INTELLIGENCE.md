# Threat intelligence integration

Implemented on 11 October 2026 IST in the existing dashboard. All added endpoints use public access without new API keys. [Live collection evidence](threat-source-live-verification.json) records provider results and validated counts. The private `.env` was preserved.

## Where to use it

**Investigate → Threat actors & campaigns** extends Cyber intelligence (AOS-02). Search actor names and aliases, or switch to campaigns, malware, tools or techniques. Select a profile to see its source descriptions, country associations, aliases, underlying references and recent report matches. The graph shows directed historical catalog relationships and separate dashed report-context links. Select a node or edge to inspect its evidence; keyboard Enter and Space work on both.

**Investigate → Cyber intelligence** contains dated cyber reports, normalized indicators, saved SANS IP activity and the existing routing/outage tools. SANS enriches a specified public IP; it does not scan the address. Results are cached for an hour, and HTTP 429 pauses further API lookups for at least five minutes or the supplied Retry-After period.

**World map → Cyber intelligence → Cyber context** displays report country mentions and publisher-to-country links. Its purple dotted links and source pulses reuse the existing map controls, publication filters and supporting-report popups. Use seven or thirty days to include older reporting. Country centroids represent context, not physical attack origins. Unlocated reporting stays in the feed. Historical actor profiles do not create map incidents or inflate the layer count.

**Investigation cases** can retain an immutable actor profile snapshot, including its catalog version, retrieval time, original URL and licensing information. Later catalog updates do not change the saved snapshot.

Verified screens: [actor workspace](threat-actor-workspace.jpg) and [Cyber context map](cyber-context-map.jpg). The map capture shows 53 dated reports and 11 context links over thirty days; these are a subset of the 87 filtered Cyber records because vulnerability catalog entries do not contribute country-discussion links.

## Sources and actual collection

| Source | Integrated content | First validated collection | Update interval and conditions |
| --- | --- | --- | --- |
| MISP Galaxy | Actor UUIDs, names, aliases, descriptions and references | 1,060 actor profiles; version 352 | Daily. CC0/BSD dual license for catalog JSON. |
| Malpedia public actor metadata | Actor UUIDs, aliases and reference enrichment | 1,060 profiles; all UUIDs overlap the checked MISP set | Daily. CC BY-NC-SA 3.0. Shared identity does not count as independent corroboration. The dataset URL is retained because API display names are not profile-page slugs. |
| ETDA / ThaiCERT | Actor cards, naming references and country associations | 502 accepted of 503 exported cards; one malformed UUID excluded | Daily availability check. Historical database revision 2025-08-16. CC BY-NC-SA 4.0. Catalog status exposes the excluded UNC2891 entry without rewriting its identity. |
| MITRE ATT&CK Enterprise | Groups, campaigns, malware, tools, techniques and explicit STIX relationships | 1,933 supported objects including deprecated/withdrawn references; version 19.2; 18,958 active supported relationships | Daily. Current and withdrawn records are distinguished. [Copyright and complete license](licenses/MITRE-ATTACK.txt) are retained, including in stored object profiles. |
| SANS ISC diary | Dated analyst feed excerpts | 10 reports | Hourly. Linked excerpts only; original reports remain with SANS. |
| Citizen Lab | Investigations, media mentions and updates | 10 reports | Hourly. Feed metadata/excerpts; original links retained. Not every feed item is an original investigation. |
| Krebs on Security | Cybercrime investigations and incident reporting | 10 reports | Hourly. Feed metadata/excerpts; original links retained. |
| defend.network | Automated secondary briefings | 25 reports | Hourly. Explicit automated-analysis tag and evidence limitation; follow cited original reporting. |
| SANS ISC public IP API | Sensor-reported activity for a selected IP | Successful 8.8.8.8 response through the adapter | On demand, cached. CC BY-NC-SA 4.0; no resale. False positives are possible; not an actor identity service or blocklist. |

The completed import has **1,667 active actor reference identities**, 56 campaigns, 730 malware references, 95 tools and 697 techniques. Actor reference identities are not a verified count of distinct organizations: differing vendor scopes and identifiers can remain separate. MISP/Malpedia records with the same UUID share an entity. Cross-catalog MITRE resolution requires a single unambiguous cited group identifier; broad references to several groups and shared names do not merge distinct groups.

Country-context links identify what a report discusses. Actor matches use bounded literal name/alias matching in collected cyber titles and excerpts. A unique match means the name occurs in a report, not that the actor carried out the incident. Shared aliases are shown as ambiguous candidates and do not generate actor-country responsibility links. The verified snapshot contains 2 unique name matches and 56 ambiguous candidate matches; these counts will change as coverage updates.

## Collection, storage and operations

Migration 005 adds catalog state, versioned object/relationship provenance and report-match tables. Catalog knowledge is separate from `external_records` and dated dashboard events. Refreshes validate the response before an atomic update, retain the last successful snapshot after failure, and mark removed or revoked references inactive. Source quality lists catalog state, version, retrieval time, licensing and stale data. This is the latest snapshot store, not a complete immutable archive of every upstream revision.

The existing worker indexes report batches and matches aliases, queues at most one due catalog each tick, and processes at most two queued investigation jobs. Catalog requests use a single fetch attempt and bounded response sizes: 6 MB for actor catalogs and 96 MB for the Enterprise STIX bundle. Existing global feed and item limits still apply. Public report collection does not scrape full articles or private Malpedia samples.

Configuration is documented in `.env.example`: `OSINT_THREAT_CATALOGS_ENABLED=true` enables scheduled catalog refreshes; `OSINT_SANS_CONTACT` optionally supplies the contact string SANS requests in the custom User-Agent. Source quality can disable individual providers. No new social-media credentials are involved. Administrative catalog refreshes use the existing server token and fifteen-minute throttling.

Run `START.bat` to replace this checkout's running services. The startup path preserves unrelated processes, recovers abandoned project-worker leases and now retries the initial SQLite journal-mode transition to support simultaneous API/worker initialization. The consistent backup made before migration is under `data/backups/osint-20261010T190807797537Z`.

For a bounded manual collection pass, use `.venv\Scripts\python.exe scripts/collect_threat_sources.py`. It collects only the four public catalogs, four new feeds and one public SANS lookup, then writes count-only verification. It does not call credentialed providers. Prefer the normal schedule for routine use.

The versioned interfaces are `/api/v1/cyber/catalogs`, `/cyber/catalogs/{source_id}/refresh`, `/cyber/actors`, `/cyber/actors/{entity_id}` and `/cyber/activity`. Existing graph endpoints now include catalog provenance. The public dashboard country network is `/api/cyber/relations`.

## Validation and remaining limits

The backend suite covers source identity resolution, shared aliases, broad subgroup references, revoked records, malformed ETDA identities, failed refreshes, immutable case snapshots, public-IP validation, API backoff, source evidence and migration concurrency. Browser checks cover the live actor graph, source evidence, saved IP activity, report filtering, context-overlay counts and the existing dashboard controls. Production build and Python lint pass.

No automatic organization attribution, campaign-victim geolocation, exploit verification or attack-route inference was added. Malpedia/ETDA non-commercial licenses and publisher excerpt terms remain attached to the data; broader redistribution requires reviewing them. Shadowserver scraping and services requiring new authentication remain excluded, as described in the [source assessment](THREAT_ACTOR_SOURCES_RESEARCH.md).

# Threat Observatory integration assessment

Implementation follow-up: [Cyber infrastructure observations](CYBER_OBSERVATIONS.md). The assessment below records the pre-integration review.

Reviewed 15 October 2026. Scope: the cybersecurity collection, data models, persistence, investigation features, map interfaces and relevant tests in Signal Atlas (`E:\RESEARCH\TEST_BED\OSINT`) and Threat Observatory (`E:\RESEARCH\TEST_BED\TEST_27B\threat-observatory`). This is an integration assessment, not a full security audit. No application code, configuration or production data was changed.

## Recommendation

**Yes, selected capabilities would be useful. Adapt individual collectors and the IP investigation workflow into Signal Atlas; retain Signal Atlas's worker, database, actor catalogs, evidence model and map.**

Threat Observatory supplies infrastructure observations: scanning IPs, honeypot requests, proposed malware indicators and DDoS aggregates. It has no named actor catalog, actor identity resolution or evidence-backed actor attribution model. Its `ThreatEvent` has an IP and country, but no actor, campaign, technique or attributed victim fields. Importing it therefore adds activity coverage, not verified knowledge about who conducted an attack.

For named actor research, Signal Atlas already provides the more useful foundation in `backend/advanced/threats.py`: MISP Galaxy, Malpedia, ETDA and MITRE ATT&CK, source profiles, aliases, explicit catalog relationships, ambiguous-name handling and report matches. Keep that foundation and connect new observations through cited indicator and malware relationships.

## What is already present

| Capability | Signal Atlas | Threat Observatory | Integration consequence |
| --- | --- | --- | --- |
| Named actors and relationships | Versioned catalogs, identifiers, aliases, campaigns, malware, tools and techniques | No actor model or catalog | Keep the current actor workspace. |
| Reported attribution | Actor wording, attacker/victim roles and source evidence | Primarily IP observations | Keep the current attribution rules. |
| Provider observations | Bitdefender, BunkerWeb, Imperva and Radware adapters | DShield, ISC honeypots; four optional adapters | Selected new providers can extend coverage. |
| IP investigation | Indicator normalization/evidence, cached SANS lookup and RIPE routing lookup | Per-IP history and source counts | Add observation history to the existing cyber workspace. |
| Collection | Separate worker, source registry, leases, persisted status/backoff, bounded HTTP and batch writes | Polling loops inside API lifespan | Use the existing worker. |
| Map | MapLibre, supported country routes, distinct attribution and traffic metadata | Separate Three.js globe and WebSocket client | Reuse existing map rendering. |
| Anomalies | Reporting-volume, regional and cross-category comparisons | Short-window country/kind detector | A provider-specific detector is optional later work. |

Read-only queries of the local databases found 1,667 active actor reference identities and 1,073 normalized indicators in Signal Atlas. Actor reference identities do not necessarily represent distinct organizations. Threat Observatory held 703 rows: 200 DShield scan observations, 502 ISC honeypot aggregates and one derived anomaly. Its stored source observations were dated 13-14 October 2026 UTC. The four optional providers contributed no stored rows in that database. These are inspection-time counts, not global attack totals or proof of current provider availability.

## Candidate capabilities

| Candidate | Value | Recommendation and prerequisites |
| --- | --- | --- |
| DShield top IP collection | Adds scheduled scan-activity coverage to the existing on-demand SANS lookup. Small configured result set, no new key. | **First implementation.** Adapt the XML parsing, validate IPs, retain reporting day and report/target counts. Identity must describe the daily aggregate, not the polling hour. |
| ThreatFox | Adds indicators and provider-reported malware associations, which can connect to investigation evidence. | **High value after rewriting the parser.** Requires an Auth-Key. Preserve IOC ID/type/value, first/last seen, malware identifier, source confidence and references. Support non-IP indicators without inventing map coordinates. |
| ISC web honeypots | Adds observed request-path and user-agent context. | **Second stage.** Fix per-day grouping, describe probes rather than confirmed intrusions, and bound downloads before parsing. Avoid the donor's broad default collection until its payload cost is measured. |
| Cloudflare Radar | Adds a DDoS protocol trend chart. | **Optional aggregate panel.** Requires a token, corrected endpoint contract, complete time buckets and explicit units. A global protocol percentage is not an individual attack or country route. |
| GreyNoise | Adds context to an IP selected by an analyst. | **On demand only initially.** Rewrite against the documented IP lookup API and account quota; do not port the assumed bulk feed. |
| P0H | Proposed additional honeypot source. | **Defer.** The adapter assumes an endpoint and response shape; this assessment did not establish a provider contract, entitlement or successful collection. |
| Per-IP history | Shows when and where providers reported an indicator. | **Reuse the workflow idea.** Extend existing indicators, evidence links, cases and SANS activity views; derive first/last seen correctly. |
| Risk score, anomaly engine and WebSocket hub | Additional sorting, alerts and streaming. | **Do not copy as implemented.** Correctness and delivery problems are described below. They are not needed to add the useful feeds. |

The official [SANS API documentation](https://isc.sans.edu/api/) documents daily top-IP aggregates and user-agent-filtered honeypot reports. It requests an identifying User-Agent, prohibits resale and states CC BY-NC-SA 4.0 terms alongside permission to protect an organization's own network. DShield and ISC honeypots belong to the same provider family; different adapter IDs alone do not establish independent corroboration.

The [ThreatFox API](https://threatfox.abuse.ch/api/) requires an Auth-Key and documents `ioc`, `ioc_type`, `threat_type`, `first_seen`, malware identifiers and references. Preserve those fields. A malware association remains a provider assertion, and commercial use can have different access terms.

[GreyNoise documents a per-IP Community API](https://docs.greynoise.io/reference/getcommunityip), using `/v3/community/{ip}` and the `key` header. The donor instead calls `/v3/community/noise`, supplies `GNOISE-ApiKey` and expects a list. That is incompatible with the documented Community lookup contract; an authenticated bulk feed was not verified.

The [Cloudflare layer-3 API documentation](https://developers.cloudflare.com/api/go/resources/radar/subresources/attacks/subresources/layer3/) describes dimension-specific time-series routes. The donor's bare `/attacks/layer3/timeseries_groups` request omits that dimension. Treat this adapter as requiring contract correction and authenticated validation, rather than as an already working integration.

## Findings that prevent a direct merge

The donor includes `CODE_REVIEW_27B.md`, dated 14 October, listing 13 defects. The findings below were checked against the current code. Numerical reproductions in this assessment used temporary SQLite databases, mocked HTTP and synthetic reserved IPs; they did not alter either live database.

| Finding | Evidence from this assessment | Integration impact |
| --- | --- | --- |
| ThreatFox discards documented responses | A successful mocked response containing one `ip:port` IOC returned zero records; `last_success` was set and `last_error` stayed empty. `observatory/sources/threatfox.py` requires nonexistent `ip`, `threat` and `date` fields. | Rewrite normalization and API-status handling; a healthy HTTP response must not hide a schema failure. |
| Repeated sightings count as corroboration | Two DShield observations for one IP in different buckets scored 9.2 and 21.2. The latter was marked corroborated despite there being only one distinct source. See `observatory/pipeline.py:111` and `observatory/storage.py:113`. | Do not map this flag to Signal Atlas's Corroborated confidence. Establish independent source families and retain sighting overlap separately. |
| Independent anomaly IDs collide | Emitting US/scan and DE/intrusion alerts for the same window produced two broadcasts but only one stored anomaly. `_emit_anomaly()` omits series identity from its dedup key. | An alert ID needs provider/series/window identity; broadcast only after successful persistence. |
| Empty windows are absent from the baseline | Six windows of 20 events, a long quiet gap, then 11 events produced zero alerts. The detector retained occupied historical windows instead of the immediately preceding time windows. | Redesign baseline, warm-up, restart and late-arrival behavior before using its alerts. |
| ISC merges separate reporting days | One hit on each of two days for the same IP became one two-hit row timestamped on the earlier day. | Key daily observations by day and IP; update aggregate counts without turning a revision into a new attack. |
| DShield polling manufactures new identities | Identical mocked daily payloads fetched an hour apart had different dedup IDs. `observed_at` is the local fetch time. | Store reporting interval separately from retrieval time; stable provider/day/IP identity prevents count inflation. |
| IP history mishandles arrival order | Upserting timestamps 200 then 100 yielded `first_seen=200`, `last_seen=100`. | Use timestamp minima/maxima and define whether history counts observations, revisions or requests. |

Static checks also confirmed that `api/ws.py` awaits client sends sequentially without a send deadline; the ingestion pipeline awaits that broadcast. `observatory/geo.py` tries plain HTTP geolocation first. Source fetches load response bodies without Signal Atlas's byte bounds, and `SourceAdapter.safe_fetch()` can shorten Retry-After to its breaker cooldown. These implementations should not replace the existing worker and `SafeHTTP`.

The 0-100 risk score is a hand-weighted priority heuristic, not an estimated probability of compromise. With the shipped configuration, the largest configured score is 26.8, including the 12-point corroboration bonus. Porting it as severity or confidence would introduce a new meaning without calibration. Keep provider confidence, evidence confidence, priority and incident severity as separate concepts.

## Integration design

### Use existing collection and evidence interfaces

Implement ordinary `Connector` subclasses with `fetch(SafeHTTP)` and `normalize(record) -> Report`, registered through `backend/connectors/registry.py`. Run them through `backend/worker.py`. Retain the existing source permissions, configuration, collection leases, status reporting, request bounds and backoff. Provider credentials belong in `backend/config.py` and documented `.env.example` entries.

Do not introduce a second FastAPI app, second operational database, embedded collection loops, PyYAML configuration, aiosqlite storage layer or the donor dashboard. Python/FastAPI/httpx compatibility makes adapting parsers straightforward; it does not make the databases interchangeable. Both databases even have an `events` table, but their columns, identifiers, timestamps and confidence values differ.

### Preserve observation meaning

Keep named actors in the current catalog tables and dated reports in the current report/evidence system. Use existing `cyber_indicators` and `indicator_evidence` for normalized indicator identity and citations. Add a migration for structured observation fields where needed: provider record ID, indicator ID, reporting interval, first/last seen, retrieval time, count and unit, malware reference and geolocation basis. Keep provider revisions distinct from new observations.

The existing indicator indexer in `backend/advanced/processing.py` extracts indicators only from category `cyber`. A new report written as category `threat` will not automatically populate those tables. Also, the current URL normalizer rejects nonstandard ports. Feed structured IOC fields through an explicit typed normalization path rather than assuming the text extractor handles every IOC format. Give provider observations an evidence classification distinct from the current `mentioned_in_report` label.

For a DShield item, use a stable identity such as source + reporting day + normalized IP. Store SANS report and target totals as daily aggregate values, with a retrieval timestamp. For ISC, include reporting day and IP. For ThreatFox, prefer the provider IOC ID and preserve its native type; retain port separately from the IP identity. Keep non-geographic domain, URL and hash observations searchable without assigning a location.

### Keep geography separate from responsibility

Signal Atlas's `ThreatMetadata` already rejects actor/victim attribution on `observed_traffic` and `detection` records. Preserve that validation. An IP geolocation describes infrastructure, not an actor's nationality. A honeypot request does not establish compromise or identify an affected organization's country.

Show a country point only when the provider or an explicitly sourced geolocation lookup supports it, and state the geographic basis. A source IP without a supported target produces no attacker-to-victim arc. Global Radar aggregates belong in a chart, without invented countries. Reuse `src/threats.js`, `src/cyber-routes.js` and the existing map interfaces for compatible observations.

The current public threat-map adapter deliberately strips IPs and keeps bounded country samples. Put detailed IP history in the investigation evidence path rather than replacing those sanitized samples with donor payloads. If a new collector uses `telemetry=True`, update retention registration too: `Database.prune_threat_telemetry()` currently accepts only four named vendor sources and raises for other IDs.

### Connect malware observations to actor research with evidence

For example: ThreatFox asserts an IOC is associated with a malware family; a catalog documents that an actor uses that family. Display both cited relationships and their dates. That path identifies an investigative lead. It does not establish that the actor operated the observed IP, because families and tools can be shared and infrastructure can change hands.

Prefer explicit provider/catalog identifiers for malware linkage. Preserve ambiguous aliases. Do not promote the current name-match results or historical catalog edges into incident responsibility, and do not infer ATT&CK techniques from a generic scan or blocking reason.

## Suggested implementation order

1. **DShield and structured observation storage.** Add the connector, daily identity, update semantics, source metadata and evidence links. Extend the existing IP detail workflow. This provides the first useful addition without new credentials.
2. **Corrected ThreatFox integration.** Add optional credentials, validate API status and typed IOC responses, preserve malware references and expose cited investigation links. Leave it visibly unconfigured when no key is supplied.
3. **Bounded ISC collection.** Measure payloads, choose a narrow collection scope and keep daily aggregates separate. Extend retention and explain sample coverage.
4. **Optional Radar and GreyNoise.** Add Radar as an aggregate chart after authenticated validation; add GreyNoise as a cached, quota-aware selected-IP lookup.
5. **Provider-specific activity alerts, if useful after collection history exists.** Compute comparable per-provider series with explicit units and coverage. Handle zero windows, outages, restarts and late records. Exclude daily snapshots and provider sampling changes from incident-count interpretations.

Before shipping the first two stages, verify documented response fixtures, repeat-poll idempotence, aggregate revisions, malformed/private IP rejection, UTC interval handling, IP/port parsing, unsupported IOC types, provider errors, source-family independence, unknown geography, retention and evidence deletion behavior. Check that new observations appear in search/cases and cannot produce unsupported actor attribution or map routes. Additional real-provider validation is needed for authenticated integrations.

## Validation performed

- Signal Atlas: 102 passed across `test_threats.py`, `test_threat_activity.py`, `test_threat_maps.py`, `test_threat_tables.py`, `test_attack_vectors.py` and `test_advanced.py`; one Starlette/httpx deprecation warning.
- Signal Atlas JavaScript: 15 passed across `threats.test.mjs`, `cyber-routes.test.mjs` and `geo-lines.test.mjs`.
- Threat Observatory: its complete existing pytest suite passed, 16 tests. It has no source-adapter contract or pipeline integration tests covering the failures reproduced above.
- Independently reproduced seven donor correctness issues described in the findings table using temporary databases and mocked inputs.
- Inspected both local databases in read-only mode and checked current official SANS, ThreatFox, GreyNoise and Cloudflare documentation.

No fresh ingestion, authenticated provider calls, browser/WebGL checks, production build or whole-repository security audit was performed. No services were started, stopped or restarted. This review adds only this assessment document to Signal Atlas.

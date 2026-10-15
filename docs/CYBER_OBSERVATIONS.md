# Cyber infrastructure observations

Implemented 15 October 2026, following the [Threat Observatory assessment](THREAT_OBSERVATORY_INTEGRATION_REVIEW.md). Signal Atlas owns collection, storage, evidence, cases and rendering. No second application or donor database is required.

## Use the workspace

Enable **Cyber infrastructure** under **Intelligence layers** on the main map. Teal CI symbols and count clusters show country-located infrastructure observations. The provider selector filters DShield, ISC honeypots or ThreatFox independently of **Cyber: Threat Actors**. The coverage line shows located and unlocated totals; unsupported or unknown locations remain in the feed. Hover a marker or select a feed card for provider units, reporting intervals, country estimate provenance and the original citation. **Investigate indicator and save evidence** opens the indicator workspace.

Locations are illustrative country centres derived from an IP country estimate, not precise host coordinates, actor nationality, victim locations or evidence of a successful intrusion. No attacker-to-victim routes are created. Domain, URL and hash indicators remain unlocated; the application does not resolve them or contact observed infrastructure. The Countries ribbon includes this layer in **Intel** activity; country mentions remain a separate measure.

Open **Investigate → Cyber intelligence** and select **Provider observations** from the view selector. Filter by provider or search for an IP, indicator or malware name. Select a record to inspect its provider, reporting interval, retrieval time and counts. Save the original observation to a case to retain an immutable snapshot.

Daily report totals, target-host totals, matching honeypot requests and indicator records have different units. Revisiting a daily aggregate updates its existing record. Multiple observations from the same provider do not establish independent corroboration. DShield and ISC honeypots share the `sans_isc` provider family.

The **Indicators** view includes structured provider evidence. ThreatFox URLs may contain nonstandard ports; those indicators remain searchable without being fetched. Provider malware references are matched against catalog references first, with exact-name candidates as a fallback. Select a related malware reference to inspect its historical catalog graph. A historical actor-to-malware relationship does not establish that the actor operated an observed indicator.

**DDoS protocol trends** displays Cloudflare Radar hourly global protocol percentages, when configured. Missing measurements remain gaps. Radar observations use a separate aggregate table and do not create incidents, countries or map routes. The chart has a readable list of its latest 24 protocol measurements.

**Look up an indicator → GreyNoise** performs a selected public-IP lookup using the configured key. Benign classifications and unknown results remain visible. Results are cached for 24 hours and provider rate-limit cooldowns apply. Saved results are available through **Saved GreyNoise IP context**.

## Providers and configuration

| Source ID | Default | Configuration and coverage |
| --- | --- | --- |
| `dshield` | Enabled | Keyless daily top-IP aggregates, checked hourly. `OSINT_DSHIELD_LIMIT=50` bounds the requested result set to 1-100. |
| `isc_honeypots` | Disabled | Opt-in matching web honeypot requests for the previous completed UTC day. `OSINT_ISC_HONEYPOTS_USER_AGENT=jndi:ldap` is a narrow configurable filter. Downloads are capped at 2 MiB. Probes do not establish intrusion. |
| `threatfox` | Access required | Set `OSINT_THREATFOX_AUTH_KEY`. Hourly collection requests indicators first seen in the last day. Stores supported IP/port, domain, URL and hash records with provider IDs, confidence, malware references and source timestamps. |
| `cloudflare_radar` | Access required | Set `OSINT_CLOUDFLARE_RADAR_TOKEN` with the necessary provider entitlement. Collects all returned hourly protocol buckets, checked hourly. |
| `greynoise` | Disabled without key | Set `OSINT_GREYNOISE_API_KEY`, then enable the provider in Source quality. Selected-IP lookup only, with the provider account quota. |

`OSINT_DSHIELD_ENABLED` and `OSINT_ISC_HONEYPOTS_ENABLED` set initial source registration defaults. Existing source enable/disable choices are preserved in **Source quality**. To opt into ISC after initial registration, configure its UA filter, reload the backend/worker, then enable its source there. Credentials stay in the backend `.env`; they are not accepted or stored in the browser. Configuration changes require reloading the API and worker. Vite can keep running.

`OSINT_SANS_CONTACT` supplies optional contact text in the SANS User-Agent. Retain provider attribution and applicable usage terms. SANS top-IP records are observations, not an automatically actionable blocklist. Source quality displays access requirements, failures, rejected/truncated records and freshness.

## Storage and scheduling

Migration 007 adds `cyber_observations` and `cyber_ddos_series`. Indicator identity and evidence reuse `cyber_indicators`, `indicator_evidence`, `external_records` and the existing case snapshot system. Structured evidence is written in the same transaction as the report and survives subsequent indexing. Corrected indicator values replace their previous evidence association. First/last-seen extrema are recalculated from retained evidence.

Migration 008 moves observation events into the independent `infrastructure` category while preserving event IDs, report IDs and citations. Existing immutable case snapshots retain their original content.

The worker enriches public-IP countries independently, up to ten lookups per minute with serial pacing. [IPwho.is](https://ipwhois.io/documentation) receives only the selected public IP through HTTPS; country results are cached for 24 hours and unknown results for an hour. Provider cooldowns and a persisted daily request budget apply across worker and manual runs. `OSINT_INFRASTRUCTURE_GEO_ENABLED=false` disables new lookups; `OSINT_INFRASTRUCTURE_GEO_DAILY_BUDGET=250` sets the default local daily cap (maximum 750). Cached country estimates retain retrieval and expiry timestamps; stale estimates are marked in evidence details. Review the provider's terms for your deployment. A bounded manual pass uses `python -m scripts.geolocate_infrastructure --limit 50` without opening a server port.

Infrastructure observations expire after `OSINT_CYBER_OBSERVATION_RETENTION_DAYS` (default 30, supported range 1-180). Cleanup runs during collection and normal maintenance. Radar aggregates expire after 30 days. Immutable saved case snapshots follow the existing case retention policy.

The normal worker registers and schedules these adapters. For one bounded pass without starting a server:

```powershell
.\.venv\Scripts\python.exe -m scripts.collect_observatory --source dshield
```

Other accepted source IDs are `isc_honeypots`, `threatfox` and `cloudflare_radar`. Repeat `--source` to select several. The command checks enablement, existing collection leases and persisted deadlines. On a pre-007 database it makes an online SQLite backup before applying migrations. The backup excludes public-discussion snapshots under the existing backup policy. It never restarts application services.

Outbound TLS combines certifi's public roots with installed system roots. Certificate verification and hostname checks remain enabled. This was necessary for the installed CA on the Windows development host; no insecure TLS fallback was added.

## Validation

Validation passed: 273 backend tests, 42 JavaScript tests, four browser tests against the existing servers, the production build, changed-file Python lint and frontend formatting. The Vite process was preserved; the API and worker were reloaded to serve the integration.

Provider contracts, typed normalization, idempotent daily updates, corrections, source families, indexing, retention, API access, case immutability, reference-based malware linkage, Radar gaps and GreyNoise caching are covered by `tests/backend/test_cyber_observations.py`.

Focused browser verification uses the existing server only:

```powershell
.\node_modules\.bin\playwright.cmd test --config playwright.existing.config.js
```

Three browser tests use isolated synthetic network responses and never seed the live database. The infrastructure layer browser test checks live rendered clusters, hover evidence, provider filtering and layer visibility. Live verification on 15 October 2026 located all 50 retained DShield observations at country centres. Country enrichment, quotas, provider backoff, category migration and public filters have additional backend coverage in `tests/backend/test_infrastructure_layer.py`. ThreatFox, GreyNoise and Radar authenticated live collection could not be exercised because their keys are not configured on this host. ISC is installed but remains opt-in. P0H and the donor's scoring, anomaly engine and WebSocket hub were not incorporated.

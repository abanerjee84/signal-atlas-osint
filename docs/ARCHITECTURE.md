# Architecture and processing rules

## Processes and interfaces

`src/` is a vanilla ES module application. It reads bounded REST responses and never calls intelligence providers or OpenRouter directly. Country geometry and the MapLibre module worker are served locally. ECharts imports only the used chart types and components. deck.gl is unnecessary for the present point and heatmap overlays.

`backend/main.py` owns validated REST endpoints. Synchronous database reads run in FastAPI's thread pool; OpenRouter requests use async HTTPX with two concurrent requests at most. The API performs no scheduled collection. Read-only dashboard requests continue during AI outages.

`backend/worker.py` schedules adapters independently, with two concurrent connectors by default and no overlapping job for a source. SQLite leases prevent simultaneous work on the same job. Collection is bounded to 480 seconds per source, response bytes and record count. Writes commit in batches of at most 100. The scheduler records heartbeat and next-run times; a protected refresh endpoint schedules a source for the next pass. Run only one worker service for predictable provider pacing.

Each connector implements `fetch`, `normalize`, metadata and access requirements. Shared services validate normalized records, preserve raw records, cluster reports and record status. A connector's safe error message does not contain its request URL or token. Normalization failures count as rejected records and do not stop valid records.

## Data and time

The versioned migrations create events, separate supporting reports, raw payloads, connector status, worker heartbeat, daily aggregates, AI attempts and cache, job leases, and evidence-review history. SQLite uses WAL, foreign keys, busy timeouts and category, country, geographic and temporal indexes.

`occurred_at` can be unknown. `published_at` is the source's publication or explicitly described observation/first-seen time. `ingested_at` is the original ingestion time; later revisions change `updated_at`. The default event filter uses occurrence time with publication fallback. Users can select publication or ingestion instead. Source details show all three.

Sentiment has its own report dataset and always applies the requested period to each source report's publication time. It scores the matching source wording, not the primary event headline. This prevents older cluster members from being treated as current samples. The timeline's second axis shows the daily mean headline score, including when an hourly volume axis repeats a day's mean.

## Location

Measured points retain their provider coordinates and uncertainty. Country assignment uses point-in-polygon against Natural Earth 1:110m geometry; it is approximate near borders and coastlines and is not a geopolitical claim. No external geocoding requests are made.

A single explicit country name in a news headline provides regional context at Natural Earth's representative point. The marker is hollow and the detail says that it is not an incident coordinate. Multiple country mentions, unsupported cities and publisher country metadata do not produce inferred event coordinates. Cyber vulnerability records remain unlocated. Filtering a map extent excludes unlocated records; those records remain searchable in unrestricted views.

Natural Earth is [public domain](https://www.naturalearthdata.com/about/terms-of-use/). Its geometry, original download checksum and excluded non-ISO features are recorded in `public/MAP_LICENSE.txt`. Illustrative boundaries do not resolve disputed sovereignty.

## Deduplication

Identical `(source_id, external_id)` is a source revision. For narrative reports, canonical source URLs remove known tracking parameters and join copies from different collectors. Original metadata keeps the supplied URL.

Candidate narrative clusters share a category and country, are within 12 hours, share at least four significant title tokens, and meet a Jaccard overlap of 0.8. Unknown occurrence times require 0.95. When both locations exist, both coordinates must differ by at most 0.5 degrees. At most 150 candidates are inspected. Geographic distance is a conservative coordinate threshold rather than a calibrated distance model; entity overlap is title-token overlap rather than named-entity resolution.

Earthquakes, thermal detections, aircraft, vessel observations and cyber catalog entries never merge merely because they share a landing-page URL or title. Each retains its provider observation ID. Original source reports remain retrievable after narrative clustering. This clustering is conservative; it does not claim full semantic correlation or independent corroboration.

## Evidence classification

Classification is deterministic or explicitly reviewed by an authenticated analyst:

| Label | Rule |
| --- | --- |
| Verified | A USGS provider-reviewed instrumental observation or CISA authoritative catalog membership. Verification covers that observation/catalog fact, not every description, cause or consequence. An analyst can choose this label only with a qualifying cited report. |
| Single-source | Default reported claim, institutional announcement, tracking observation or thermal detection. Copies of the same URL do not upgrade it. |
| Unverified | An automatic USGS observation awaiting provider review, or an analyst's documented unresolved assessment. |
| Corroborated | At least two cited publisher hosts and an analyst's explicit confirmation that reporting is independent, with written basis. Different hosts alone do not establish independence. |
| Disputed | At least two cited source reports and an analyst's explicit confirmation of conflicting evidence, with written basis. |

Reviews are stored with UTC time, cited report IDs and confirmations, and survive subsequent source refreshes. This release has one protected administrator role using a shared bearer token; it does not provide individual analyst accounts or per-person audit identity. A review can become outdated when a source revises its report; analysts must reassess relevant reviews. The LLM cannot set evidence status.

Severity is separate from confidence. USGS uses documented magnitude thresholds, ACLED uses reported fatality thresholds, and CISA catalog membership derives high severity. Other sources remain unknown unless they supply a documented rule. No severity implies tactical certainty.

## AI boundaries

The server builds evidence packets from at most 30 chosen events, three reports per event and 1,200 description characters per report. A filtered briefing selects the newest 20 matching events, prioritizing high/critical severity within that set. The provider model catalogue is checked and cached for one hour. Free-only mode requires both prompt and completion prices to be zero; no paid fallback is enabled by default.

Every outbound completion attempt reserves a local UTC-day budget slot in an atomic transaction, including failures and retries. Model checks and cache hits do not consume that budget. Two attempts per configured model use bounded backoff; optional fallback stays subject to the same budget and pricing policy. An identical request cannot run concurrently under its database lease. Whole analysis time is bounded at 540 seconds, including waiting for a slot. Refresh never invokes inference.

Output must match the claims/limitations schema. Every claim must cite an event/report pair in the supplied packet; arbitrary source URLs are not accepted from the model. References are attached by the server. Facts, interpretations and contradictions are separate claim kinds. Cache keys include model policy, question and source content; source revisions invalidate their matching cache entry.

Citation validation proves membership in the evidence packet, not factual entailment. Analysts must check generated text against cited reports. The prompt instructs the model to ignore instructions inside source content, but model compliance is not a formal prompt-injection guarantee. Source and model text are rendered through text nodes, and no output is executed as SQL, JavaScript or commands.

## Bounds and security

API event pages hold at most 1,000 events; the client normally loads 500 and caps accumulated pages at 5,000. Timeline queries return at most 3,000 category buckets. Sentiment reads at most the newest 5,000 distinct URLs and discloses truncation; raw source details have the same configured response-size bound as ingestion. Natural Earth boundaries are local and modest in size.

HTTP request bodies are capped at 64 KiB, including chunked bodies. A bounded 2,048-client counter permits 120 requests per minute per peer. Nginx adds shared rate limits and overwrites forwarded client addresses. AI, source-refresh, evidence-review and maintenance endpoints require the server token; missing configuration disables protected functions. SQL uses bound parameters, displayed untrusted content uses safe DOM APIs, and feed XML uses defusedxml.

Default provider destinations are fixed approved HTTPS hosts. Configured feed hosts require an exact allowlist, public DNS addresses, port 443 and no redirects. DNS rebinding remains a deployment concern; an outbound firewall/proxy that denies internal ranges provides a stronger boundary. Administrative source configuration comes exclusively from protected environment files.

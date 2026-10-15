# World Monitor features and Signal Atlas incorporation plan

Reviewed 15 October 2026. Target: [worldmonitor.app](https://www.worldmonitor.app/) and the official [koala73/worldmonitor](https://github.com/koala73/worldmonitor) project, not similarly named sites or forks.

## Recommendation

Start with saved monitoring workspaces, watchlists, change tracking, evidence-based country dossiers, and scheduled briefings. These additions build on Signal Atlas's existing map, citations, cases, threat catalogs and typed observations. Add a small number of commercially permitted infrastructure and disruption datasets next. Keep financial trading tools, predictive country scores and a new 3D engine as optional later projects.

This is a feature assessment and implementation backlog. It does not implement the features or claim that World Monitor's data, code, branding or hosted API outputs can be reused without their applicable terms.

Use the two documents together:

- **[Domain feature catalog](WORLDMONITOR_FEATURE_CATALOG.md):** individual layers, data panels, regional products, scoring systems and specialist workflows, with primary-source citations and Signal Atlas gaps.
- **This plan:** interface, personalization, AI, alerts, accounts, integrations, implementation priorities and acceptance criteria.

## Evidence and scope

The public landing page, anonymous dashboard, mission presets, command palette, panel catalog and settings were inspected in a browser. The official documentation and source were inspected for capabilities that are hidden, optional or paid. Source baseline: [`ffa31628243af9054b7f51418486d5115ab4e6dd`](https://github.com/koala73/worldmonitor/tree/ffa31628243af9054b7f51418486d5115ab4e6dd). Signal Atlas baseline: local `main` at `7793beb`.

This inventory covers the public product and published source/docs at review time. A visible control proves that the interface offers a feature, not that every upstream feed is current. Paid workflows, notifications, billing, desktop binaries and predictive outputs were not exercised. No account was created, payment made, subscription gate bypassed, notification sent or private data accessed. No source code was copied into Signal Atlas.

Documentation and the live product are not always synchronized. For example, public pages describe different country counts for resilience coverage. Exact provider/panel counts are therefore not used as capability or quality guarantees. Features documented as Enterprise should be treated as advertised contract options until demonstrated.

For reproducibility, the anonymous browser snapshot exposed **165 panel-setting entries** across the available catalog and **38 map-layer controls** in the inspected World view. These counts include topic feeds and variant-specific surfaces. They are not counts of unique analytical capabilities, healthy collectors or free features. The source-wide layer union is recorded separately in the catalog appendix.

### Status and priority

| Label    | Meaning                                                                                                 |
| -------- | ------------------------------------------------------------------------------------------------------- |
| Existing | Signal Atlas implements the core behavior; retain it and improve only identified gaps.                  |
| Partial  | A related capability exists, but the workflow, persistence or coverage differs.                         |
| New      | No equivalent product workflow was found in the inspected code.                                         |
| Access   | A connector or concept exists, but credentials, entitlement or commercial permission are prerequisites. |
| P0       | Foundation required before shared paid accounts or delivery of private customer intelligence.           |
| P1       | First product work after selecting a customer and permitted sources.                                    |
| P2       | Useful expansion after repeat use is demonstrated.                                                      |
| P3       | Optional specialization or substantial research project.                                                |
| Keep     | Preserve the existing implementation; no replacement project recommended.                               |

Effort bands describe engineering scope, not promised delivery dates: **S** is an isolated frontend or endpoint change; **M** adds a bounded workflow and persistence; **L** spans storage, jobs, UI and operations; **XL** adds a platform or substantial analytical/data-validation work. Source access, licensing, customer discovery and production acceptance are separate dependencies.

## What the public interface actually offers

The anonymous `/dashboard` exposed layer explanations, a mission selector, dashboard tabs, a 2D/3D switch, regional navigation, a time filter, keyboard search, a panel catalog and explicit locked states. The mission selector offered crisis, supply-chain, energy, news, stocks, technology, positive-news and country-monitoring presets. The command palette opened and displayed country, panel, layer and time commands. Add Panel opened Settings with searchable panel families, visibility controls and text-size options. A Resilience control and dashboard export action were visibly locked.

These are **observed controls**. Their underlying data accuracy, full persistence, paid entitlement enforcement and every panel's operation were not tested. Official descriptions are linked at each capability below so the review can be repeated. Browser observations support interface discovery, not a general performance or security certification.

## A. Map, interface and personal workspaces

World Monitor sources: [interface guide](https://www.worldmonitor.app/docs/features), [hotspots/navigation](https://www.worldmonitor.app/docs/hotspots), [map engine](https://www.worldmonitor.app/docs/map-engine), and the [public dashboard](https://www.worldmonitor.app/dashboard). Rows describe independent incorporation ideas; Signal Atlas statuses are based on local code.

| ID    | World Monitor capability                                  | Signal Atlas | Incorporation decision                                                                                                                        | Priority / effort |
| ----- | --------------------------------------------------------- | ------------ | --------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- |
| UX-01 | Mission presets                                           | New          | Save task templates such as Cyber Research, Country Watch and Conflict Reporting.                                                             | P1 / S            |
| UX-02 | Named dashboard tabs                                      | New          | Persist separate workspaces with their own filters and layout.                                                                                | P1 / M            |
| UX-03 | Reorder, resize and hide panels                           | Partial      | Existing collapse controls remain; add keyboard-accessible layout editing and reset.                                                          | P2 / M            |
| UX-04 | Move or pin the map                                       | Partial      | Add optional map/feed layout presets without replacing the map.                                                                               | P2 / S            |
| UX-05 | Universal command palette                                 | Partial      | Extend topic search to countries, cases, indicators, actions and views.                                                                       | P1 / M            |
| UX-06 | Shareable map state                                       | New          | Encode public filters, layers, time basis and camera in a versioned URL.                                                                      | P1 / S            |
| UX-07 | Regional navigation presets                               | Partial      | Add named multi-country regions beside the existing country filter.                                                                           | P1 / S            |
| UX-08 | Per-reader source preferences                             | Partial      | Separate personal feed filtering from administrator collection enablement.                                                                    | P1 / M            |
| UX-09 | Unread and recently changed items                         | New          | Track per-reader revisions and a stable last-reviewed cursor.                                                                                 | P1 / M            |
| UX-10 | Keyword monitors and highlighting                         | Partial      | Turn saved narrative topics into persistent country/entity/keyword watches.                                                                   | P1 / M            |
| UX-11 | Multi-panel country dossier                               | Partial      | Combine existing country context, activity, threats, observations and citations.                                                              | P1 / M            |
| UX-12 | Dashboard snapshot playback                               | Partial      | Keep event timeline and case snapshots; add versioned workspace snapshots separately.                                                         | P2 / L            |
| UX-13 | Dashboard CSV/JSON/PDF export                             | Partial      | Preserve case JSON/Markdown; add scoped dashboard CSV and a printable evidence brief.                                                         | P1 / M            |
| UX-14 | Keyboard panel movement and resizing                      | Partial      | Make new layout controls operable without drag gestures.                                                                                      | P2 / S            |
| UX-15 | Global and per-panel text size                            | New          | Store accessible text-size preferences and test dense evidence tables.                                                                        | P2 / S            |
| UX-16 | Mobile first-run guidance                                 | Partial      | Keep responsive styles; add a focused mobile default and onboarding.                                                                          | P2 / M            |
| UX-17 | Layer explanations and methodology popovers               | Partial      | Put location basis, units, freshness and limitations beside each layer control.                                                               | P1 / S            |
| UX-18 | Local persistent settings                                 | Partial      | Replace tab-only preferences selectively with versioned device/account preferences.                                                           | P1 / M            |
| UX-19 | Dark/light theme, fullscreen and clusters                 | Existing     | Keep current controls and MapLibre symbols.                                                                                                   | Keep              |
| UX-20 | Country/time/category filters                             | Existing     | Keep current UTC filters, unknown-location behavior and separate time bases.                                                                  | Keep              |
| UX-21 | 2D and 3D renderers                                       | New          | Optional globe adapter over common data; retain 2D as the default.                                                                            | P3 / XL           |
| UX-22 | Day/night overlay                                         | New          | Add an optional solar terminator only if relevant to a user's task.                                                                           | P3 / S            |
| UX-23 | Live broadcaster streams                                  | New          | Optional official embeds with availability states, mute and idle stop.                                                                        | P3 / M            |
| UX-24 | Webcam map/panel                                          | New          | Optional permitted stream registry with explicit coverage and source times.                                                                   | P3 / L            |
| UX-25 | Multilingual interface                                    | New          | Translate interface text separately from source content and scoring.                                                                          | P2 / L            |
| UX-26 | City/asset search                                         | Partial      | Current resolution is country-level; add a permitted geocoder and precision metadata.                                                         | P2 / M            |
| UX-27 | Specialized site variants                                 | New          | Prefer task presets in one product before separate finance/energy/tech sites.                                                                 | P2 / M            |
| UX-28 | [Custom widget builder](https://www.worldmonitor.app/pro) | New          | Start with source-linked cards from approved components. Isolate advanced custom rendering from application credentials and private evidence. | P2 / L            |

Specific source notes: [custom monitors](https://www.worldmonitor.app/docs/panels/monitors), [webcam layer](https://www.worldmonitor.app/docs/webcam-layer) and [world clock](https://www.worldmonitor.app/docs/panels/world-clock). A basic multi-timezone clock is a small optional utility, not an intelligence-data project.

## B. Briefings, AI and research output

| ID    | Capability and World Monitor evidence                                                              | Signal Atlas | Incorporation decision                                                                   | Priority / effort |
| ----- | -------------------------------------------------------------------------------------------------- | ------------ | ---------------------------------------------------------------------------------------- | ----------------- |
| AI-01 | [Personalized latest brief](https://www.worldmonitor.app/docs/panels/latest-brief)                 | Partial      | Compose an edition from an explicit evidence window and user watches.                    | P1 / L            |
| AI-02 | [Country and regional analysis](https://www.worldmonitor.app/docs/panels/regional-intelligence)    | Partial      | Add a dossier-level briefing over selected retained reports.                             | P1 / M            |
| AI-03 | [Conversational analyst](https://www.worldmonitor.app/docs/panels/chat-analyst)                    | Partial      | Add bounded conversation over selected evidence, with visible citations and cost.        | P2 / L            |
| AI-04 | [Opt-in dashboard control](https://www.worldmonitor.app/docs/panels/chat-analyst)                  | New          | Permit only validated navigation/layer actions; include pause and undo.                  | P3 / L            |
| AI-05 | [Brief reader and public share](https://www.worldmonitor.app/docs/api-brief)                       | New          | Add reviewed editions, explicit publish/revoke actions and private-by-default drafts.    | P1 / L            |
| AI-06 | [Social image editions](https://www.worldmonitor.app/docs/api-brief)                               | New          | Generate source-linked briefing cards after permission checks and review.                | P2 / M            |
| AI-07 | [Semantic/local ML](https://www.worldmonitor.app/docs/ai-intelligence)                             | Partial      | Supplement lexical FTS with optional embeddings; retain filters and source text.         | P2 / L            |
| AI-08 | [Multilingual analysis](https://www.worldmonitor.app/docs/ai-intelligence)                         | Partial      | Keep original text, identify translations, evaluate language-specific output.            | P2 / L            |
| AI-09 | [AI forecasts](https://www.worldmonitor.app/docs/panels/forecast)                                  | New          | Defer predictions until labels, calibration and outcome evaluation exist.                | P3 / XL           |
| AI-10 | [Source credibility scoring](https://www.worldmonitor.app/docs/methodology/news-credibility)       | Partial      | Expose source-quality dimensions; do not replace evidence confidence with a truth score. | P2 / L            |
| AI-11 | [Editorial briefing rules](https://www.worldmonitor.app/docs/methodology/news-digest-and-briefing) | Partial      | Deduplicate source families and distinguish commentary, updates and durable events.      | P1 / M            |
| AI-12 | [Structured intelligence and grounding](https://www.worldmonitor.app/docs/ai-intelligence)         | Existing     | Preserve citation-ID checks, labelled drafts, quotas and provider failure handling.      | Keep              |

World Monitor documents premium gates for several AI panels. This review did not generate a paid answer or verify its accuracy. Signal Atlas's structured analyses, case evidence and human review are existing assets; a chatbot should reuse them instead of introducing a second evidence model.

## C. Watchlists, notifications and integrations

The [notification contract](https://www.worldmonitor.app/docs/api-notifications) documents channel settings, filtering, quiet hours and delivery. The [briefing methodology](https://www.worldmonitor.app/docs/methodology/news-digest-and-briefing) explains editorial selection. The following are separate implementation units, not claims that Signal Atlas currently sends alerts.

| ID    | World Monitor capability                    | Signal Atlas | Incorporation decision                                                              | Priority / effort |
| ----- | ------------------------------------------- | ------------ | ----------------------------------------------------------------------------------- | ----------------- |
| AL-01 | Follow countries and topics                 | Partial      | Persistent watches with countries, entities, keywords and selected sources.         | P1 / M            |
| AL-02 | Event and threshold rules                   | New          | Define predicates over retained evidence; preview matching records before enabling. | P1 / L            |
| AL-03 | Scheduled daily/twice-daily/weekly digests  | New          | Timezone-aware scheduled editions, first as an in-app delivery inbox.               | P1 / L            |
| AL-04 | Email, Telegram, Slack and Discord channels | New          | Implement one requested channel first, with explicit recipient opt-in.              | P1 / L            |
| AL-05 | Signed outbound webhooks                    | New          | HTTPS/public-host validation, encrypted secrets and verified delivery signatures.   | P2 / L            |
| AL-06 | Browser/mobile push                         | New          | Permission request, subscription expiry handling and an in-app fallback.            | P2 / L            |
| AL-07 | Quiet hours and per-channel routing         | New          | Store timezone, severity and routing preferences with a test preview.               | P1 / M            |
| AL-08 | Delivery identity and duplicate protection  | New          | Outbox, retries, deduplication keys, expiry and a delivery audit.                   | P1 / L            |

Reuse existing worker leases and persisted jobs, but create notification-specific ownership and delivery tables. Source-health actions, on-screen reporting signals and website-change monitoring are not substitutes for a customer notification service. No messages were sent while preparing this assessment.

## D. Developer access, packaging and commercial controls

| ID      | Capability and World Monitor evidence                                                      | Signal Atlas | Incorporation decision                                                              | Priority / effort             |
| ------- | ------------------------------------------------------------------------------------------ | ------------ | ----------------------------------------------------------------------------------- | ----------------------------- |
| DEV-01  | [REST API and schemas](https://www.worldmonitor.app/docs/api-reference)                    | Existing     | Keep `/api` and `/api/v1`; add an explicit supported developer contract.            | P2 / M                        |
| DEV-02  | [MCP tools](https://www.worldmonitor.app/docs/mcp-overview)                                | New          | Start with read-only search, report detail, country summary and indicator evidence. | P2 / L                        |
| DEV-03  | [OAuth and scoped API keys](https://www.worldmonitor.app/docs/api-oauth)                   | New          | Introduce named, expiring, revocable credentials and per-account scopes.            | P0 / L for paid API           |
| DEV-04  | [Python/JS/Ruby/Go clients and CLI](https://www.worldmonitor.app/docs/sdks)                | New          | Generate one small Python client after endpoint stability; add others on demand.    | P3 / M                        |
| DEV-05  | [Agent discovery and tool descriptions](https://www.worldmonitor.app/docs/agent-discovery) | New          | Publish accurate capabilities, limits and provenance for supported read tools.      | P2 / M                        |
| DEV-06  | [Embeddable map and panels](https://www.worldmonitor.app/docs/embed-live-map)              | New          | Separate public-safe surfaces, origin controls, attribution and revocable keys.     | P2 / L                        |
| DEV-07  | [Native desktop app](https://www.worldmonitor.app/docs/desktop-app)                        | Partial      | Local browser deployment exists; defer a native wrapper and updater.                | P3 / XL                       |
| DEV-08  | [Offline/local AI](https://www.worldmonitor.app/docs/ai-intelligence)                      | New          | Optional feature; measure model downloads, device memory and quality first.         | P3 / L                        |
| DEV-09  | [WebMCP and interactive MCP apps](https://www.worldmonitor.app/docs/webmcp)                | New          | Defer until ordinary API/MCP access has users.                                      | P3 / L                        |
| SAAS-01 | [User sign-up and sign-in](https://www.worldmonitor.app/docs/accounts)                     | New          | Replace shared-token customer access with individual identities and sessions.       | P0 / L                        |
| SAAS-02 | [Account billing and subscriptions](https://www.worldmonitor.app/docs/api-commerce)        | New          | Entitlements, verified webhooks, cancellation and usage accounting.                 | P0 / L for self-service sales |
| SAAS-03 | [Team seats and invitations](https://www.worldmonitor.app/docs/accounts)                   | New          | Add organizations, member roles and owned evidence before shared accounts.          | P0 / XL for teams             |
| SAAS-04 | [Account deletion and billing lifecycle](https://www.worldmonitor.app/docs/accounts)       | Partial      | Existing soft-deleted cases are not an account-erasure system; add explicit policy. | P0 / L                        |
| SAAS-05 | [Plan-specific quotas](https://www.worldmonitor.app/docs/rate-limits)                      | Partial      | Keep global safeguards; add atomic per-customer budgets and usage display.          | P0 / L                        |
| SAAS-06 | [Enterprise deployment and support](https://www.worldmonitor.app/pro)                      | Partial      | Existing Ubuntu services are a base; define restore, update and support contracts.  | P2 / L                        |
| SAAS-07 | [Enterprise SSO and white-label options](https://www.worldmonitor.app/pro)                 | New          | Advertised options, not tested here. Implement only for a contracted requirement.   | P3 / XL                       |

Private cases, evidence files, jobs, exports, search results, caches and notification destinations all need organization-level authorization for a shared SaaS. Billing alone does not provide isolation. A customer-specific deployment can be an earlier commercial offering, subject to permitted sources and its own operational acceptance.

## E. Domain additions to evaluate first

The [full domain catalog](WORLDMONITOR_FEATURE_CATALOG.md) contains the individual features and their citations. These are the recommended integration groups rather than a replacement for those rows.

| Candidate                                | Current baseline                                                     | Recommendation and prerequisites                                                                              |
| ---------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Internet/service disruption layer        | RIPE/IODA investigation observations; optional Radar DDoS aggregates | Add a separate outage view and incident basis. Protocol share is not an outage measurement.                   |
| Undersea cables and landing points       | No equivalent registry                                               | Add a licensed, versioned asset registry, then link relevant outage evidence with stated uncertainty.         |
| Airport/airspace disruptions             | Aircraft tracks and registry details                                 | Add official delay/closure/NOTAM coverage with source times and jurisdiction limits.                          |
| Weather, flood, storm and volcano events | Earthquakes, FIRMS and humanitarian reports                          | Add a small set of official hazard feeds; retain different units and coverage.                                |
| Sanctions entity/change monitoring       | Sanctions reporting and official feed sources                        | Add explicit list/version/change models before entity exposure or compliance claims.                          |
| Ports, chokepoints and maritime flow     | Configurable maritime adapter; no default licensed vessel feed       | Add static port/chokepoint reference layers first. Live vessel aggregates require authorized coverage.        |
| Protests, conflict and displacement      | Conflict reporting plus access-dependent ACLED                       | Separate event observations from news mentions; add displacement stocks and flows without mixing them.        |
| GPS/navigation interference              | No equivalent measurement feed                                       | Useful aviation adjunct if a permitted dataset is available; display reporting window and measurement limits. |
| Nuclear/radiation/thermal monitoring     | FIRMS thermal detections                                             | Keep facilities, radiation measurements and thermal anomalies separate. None alone confirms an attack.        |
| Energy assets and disruption logs        | Economic/energy reporting                                            | Add pipelines/storage metadata and cited disruption histories; operator feeds or analyst review required.     |
| Regional/China dashboards                | Regional publishers and country filters                              | Build task presets first. China disclosures/nowcasting require a dedicated ingestion and language program.    |
| Markets, commodity and macro panels      | Economic reporting, not quote/time-series infrastructure             | Add only for a selected customer; data licensing and quote delay semantics are separate work.                 |
| Country instability/resilience           | Reporting surges, cross-category activity and sentiment              | Keep those current measures. Do not relabel reporting volume as validated geopolitical risk.                  |
| Supply-chain routes and scenarios        | No network/trade-flow model                                          | Later research product: build a validated graph, unit-consistent dependencies and scenario assumptions first. |

## F. Preserve existing capabilities

Signal Atlas already has map clustering, layer topic search, UTC periods, geographic filters, live aircraft interpolation, orbital propagation, source health, bounded collection, sentiment samples, threat catalogs, typed infrastructure evidence, local indexed search, cases, notes, relationship graphs and citation-checked AI analyses. These should not be reimplemented just to match World Monitor naming.

Local evidence for the comparison:

- [Dashboard state and rendering](../src/main.js), [map](../src/map.js), [country ribbon](../src/country-ribbon.js), [topic search](../src/layer-search.js).
- [Investigation screens](../src/advanced.js), [versioned endpoints](../backend/advanced/api.py), [case persistence](../backend/advanced/repository.py).
- [Threat catalogs](../backend/advanced/threats.py), [infrastructure observations](../backend/cyber_observations.py), [country estimates](../backend/infrastructure_geo.py).
- [Worker](../backend/worker.py), [investigation jobs](../backend/advanced/tasks.py), [website monitoring](../backend/advanced/watch.py), [AI](../backend/ai.py).
- [Architecture/evidence rules](ARCHITECTURE.md), [investigations](ADVANCED_OSINT.md), [cyber observations](CYBER_OBSERVATIONS.md), [current README](../README.md).

## G. Recommended build sequence

### Stage 0: commercial and identity foundations

Choose a pilot user and source set. Record per-source commercial display, retention, export and derivative permissions. For a shared paid website, add SAAS-01/03/04/05 before exposing private customer records; add billing for self-service checkout. For an isolated managed pilot, define access and backup ownership explicitly instead of pretending the current shared administrator token is a multi-user system.

### Stage 1: recurring research workflow

Build UX-01/02/06/07/08/09/10/11/13/17/18 and AL-01. Reuse the current evidence model and collector. This creates a repeatable flow: **open a saved watch, inspect what changed, review the evidence, save a finding, export a briefing**.

### Stage 2: scheduled value and one delivery channel

Build AI-01/05/11 and AL-02/03/04/07/08. Start with an in-app edition and one customer-selected delivery channel. Add editorial review, unsubscribe controls and duplicate prevention before increasing delivery volume. Neither customer destinations nor private evidence should leak into public share links.

### Stage 3: domain depth

Select two or three domain groups from section E based on pilot use. Internet disruptions, licensed cable geography, airport closures and official hazards fit the existing map. Ship collection health, provenance, coverage and unknown states with each feed. Do not enable every dataset simply because an adapter can be written.

### Stage 4: platform expansion

Add read-only MCP/API access, richer embeddings, organization sharing and licensed embeds when users request them. Evaluate specialized finance, structural country scores, route modelling, a 3D engine and native packaging as separate product decisions. Their source availability and validation costs differ from frontend feature work.

## H. Concrete acceptance checks for the first release

| Deliverable             | Observable completion condition                                                                                                         |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Saved workspace         | Save a named country/topic/provider/time-basis/layer selection, reload and recover it. Invalid old preferences migrate or reset safely. |
| Shareable map           | Open a URL in a clean browser and recover only public view state. Credentials, private queries and case identifiers are excluded.       |
| Personal source filters | One reader's preference changes their feed without disabling collection for everyone.                                                   |
| Change tracking         | A new source revision appears once as changed; refresh alone does not create a new unread item.                                         |
| Watchlist               | Explain why each record matched, retain the relevant revision and show zero matches distinctly from collection failure.                 |
| Country dossier         | Every factual block links to retained evidence with source time, location basis and missing/stale indicators.                           |
| Brief edition           | Preserve the selected window, sources and model/policy metadata. Source-family duplicates do not count as corroboration.                |
| Private/public export   | Preview what will be shared; restricted content and private notes stay out unless explicitly permitted.                                 |
| Scheduled delivery      | Restart the worker around a scheduled run without duplicate sends; quiet hours and unsubscribe still apply.                             |
| Customer isolation      | A second account cannot enumerate another account's cases, evidence files, jobs, exports, caches or delivery destinations.              |

Apply accessible labels, focus handling and keyboard alternatives to new controls. Saving must distinguish draft, pending, success and failure; failed saves retain edits. Cancel/Escape behavior and persistence ownership should be documented before implementation, following the interaction-contract review used for this assessment.

## I. Licensing and methodological decisions

World Monitor's [platform license](https://www.worldmonitor.app/docs/license) is AGPL-3.0-only, with separate MIT client packages and optional alternative licensing. Its hosted plan rights, source-code license and trademarks are distinct. For this MIT repository, the default recommendation is independently implemented functionality over properly licensed sources. Copying platform code requires a separate license/compliance decision; the feature list is not authorization to copy it.

Upstream data rights remain separate from World Monitor's implementation. In our current installation, [SANS data](https://isc.sans.edu/researchfeed.html), [OpenSky](https://opensky-network.org/about/faq) and [CNA RSS](https://www.channelnewsasia.com/rss/rssterms) require commercial-use review before a paid or advertising-supported offering. An API client license does not grant unrestricted redistribution of all upstream data.

Retain Signal Atlas's distinction between infrastructure location and attributed actors, source quality and factual truth, correlation and causation, measured values and modelled values. World Monitor documents heuristic country scores, automated attribution and analytical outputs; recreating their names or visual confidence does not validate their conclusions. A production score needs a declared purpose, versioned inputs, missing-data behavior, historical evaluation and an explanation users can inspect.

## J. Open questions and review limits

1. Which customer task is the first paid pilot: client briefings, cyber monitoring, country research or operational disruption monitoring?
2. Which sources permit commercial display, storage, exports and alerts for that task?
3. Does the first release serve isolated installations or a shared SaaS? That changes ownership and identity work.
4. Which one delivery channel and digest cadence do pilot users actually need?
5. What false-positive rate and review burden are acceptable for each alert or score?

These decisions do not block this inventory. They should select the implementation scope. Paid feature availability, commercial license terms, proprietary source quality, Enterprise contracts and live predictive performance remain unverified. Recheck official documentation and provider terms before implementing or buying access.

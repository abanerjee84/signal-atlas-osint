# Signal Atlas implementation backlog — World Monitor incorporation

Derived from [`WORLDMONITOR_INCORPORATION_PLAN.md`](WORLDMONITOR_INCORPORATION_PLAN.md) (reviewed 15 October 2026) and the
[domain feature catalog](WORLDMONITOR_FEATURE_CATALOG.md). Requirements are specified in [`SRS.md`](../SRS.md) (`OSINT-SRS-002`).

**Build order: features first.** Map layers are Phase 1, not a later domain phase. **Update this file at the end of
every phase.**

---

## Stated priorities

Recorded 2026-10-16 by the project owner:

- **All three monitoring domains are in scope:** cyber monitoring, country research, disruption monitoring.
- **No sales in the near term**, with commercial release as the end goal.
- **Map layer implementations are the highest priority**, ahead of workspaces, briefings and platform work.

These three inputs drive the ordering below. In particular, because nothing is being sold yet, identity and tenancy
work is **no longer a blocker for feature development** — it becomes a gate that must be cleared *before* the first
paid customer, not a prerequisite for the next layer.

---

## Phase order

| Phase | Name | Gate |
| ----- | ---- | ---- |
| WM-P0 | Licensing and entitlement register | — (done) |
| **WM-P1** | **Reference layers — static geometry** | WM-P0 |
| **WM-P2** | **Event layers — wire existing evidence** | WM-P1 |
| **WM-P3** | **Licensed live layers** | WM-P0 |
| WM-P4 | Saved research workspaces | WM-P1 |
| WM-P5 | Scheduled briefings and delivery | WM-P4 |
| WM-P6 | Identity and tenancy | **before first paid customer** |
| WM-P7 | Platform access and optional specialisation | WM-P5, WM-P6 |

**Why this order.** Layers are the product's visible surface and the clearest gap against the catalog. Reference
geometry goes first because it is the only layer class the product does not have at all, and it needs no collection
job, no provider key and no licence — so it can be built and proven before any gated work. Event-layer wiring follows
because most of that evidence is already collected and stored but never drawn. Licensed layers wait on WM-P0
decisions. Workspaces and briefings come after the map has something worth saving. Identity is demoted because no
customer shares the system yet, and is re-labelled as a pre-sale gate rather than a pre-feature gate.

**Status legend:** `[ ]` not started · `[~]` in progress · `[x]` complete · `[!]` blocked

---

## Layer gap summary

| Measure | Count |
| ------- | ----- |
| Registry layers present | 12 — Orbital Surveillance, Military Activity, Aviation, Cyber Threats, Fires, Day/Night, Ports, Internet Disruptions, Military Bases, Nuclear Plants, Spaceports |
| Registry layers partial | 7 — Hotspots, Conflict Zones, Ship Traffic, Protests, Natural Events, Sanctions, Armed Conflict Events |
| Registry layers absent | 38 |
| Of the absent, deliberately declined | 2 — Country Instability, Resilience |
| Of the absent, blocked on a verified source | 2 — Gamma Irradiators, Chokepoints |
| Of the absent, building next (WM-P2) | 17 |
| Of the absent, licensed/gated (WM-P3) | 9 |
| Of the absent, skipped or deferred | 10 — tech/finance geography, audience variants, Canada-only |

The reason 38 absences are **17 items** rather than 38 projects: most of the registry is static asset geometry
(bases, sites, ports, plants, exchanges) shippable as versioned offline GeoJSON with no collection job, and several
event layers already exist in the database but were never wired to a map source.

---

## WM-P0 — Licensing and entitlement register

**Priority:** P0 · **Effort:** S · **Blocks:** WM-P3 and any commercial release.

The plan's Stage 0 requires recording per-source commercial display, retention, export and derivative permissions,
and §I names SANS ISC, OpenSky and CNA RSS as needing commercial-use review. Nothing in this repository could enforce
that: `backend/connectors/registry.py` carries source metadata, but no field distinguished "public data" from "public
data we are permitted to resell".

| Item | Work | State |
| ---- | ---- | ----- |
| LIC-01 | `source_permissions` migration table | `[x]` Done — `backend/migrations/009_source_permissions.sql` |
| LIC-02 | Collector gate refusing undecided sources in a declared commercial deployment | `[x]` Done — `permission_refusal()` in `backend/worker.py` |
| LIC-03 | `docs/SOURCES.md` commercial-permission column | `[ ]` Open |
| LIC-04 | Dated record of pilot customer, task and permitted source set | `[ ]` Open — owner decision, not engineering |

**Design note.** The gate engages only when `OSINT_COMMERCIAL_USE=true`. Without it every already-configured
connector keeps collecting exactly as before. With it, any source whose decision is not `cleared` is refused. An
absent row is an open question, never a permission.

---

## WM-P1 — Reference layers: static geometry

**Priority:** P1 · **Effort:** S–M per layer · **Depends on:** WM-P0.
**First build phase.** Establishes the reference-layer contract that WM-P2 through WM-P3 all reuse.

Signal Atlas currently has **no static reference layers**. All 23 map sources in `src/map.js` (`addSource`, lines
936–1629) are derived from collected records: `events`, `density`, `aircraft`, `aircraft-trail`, `sentiment`,
`military-places`, `military-network`, `news-network`, `cyber-network`, `threat-network`, `threat-directions`,
`threat-endpoints`, `social-network`, `publishers`, `new-reports`, `regional-anomalies`, `cross-category`,
`event-selection`, `orbital-positions`, `orbital-tracks`, plus basemap `world`, `grid`, `polar-mask`.

World Monitor's `LAYER_REGISTRY` is majority asset geometry — cables, pipelines, bases, nuclear sites, ports,
chokepoints, mines, processing plants, exchanges, data centres. That is **one architectural gap, not 45 separate
ones**: record-derived layers decay with their feed, while reference geometry is versioned, licensed and shippable
offline. This phase builds the second kind.

Layers are stored as versioned GeoJSON carrying the existing `geographic_evidence` contract (`precision`, `basis`,
`source_url`, `retrieved_at`, `license_classification`) from `backend/migrations/004_advanced.sql:70`, plus a
registry version. Reference geometry is excluded from event counts, activity measures and anomaly statistics.

| Item | Layer | Registry row | Notes |
| ---- | ----- | ------------ | ----- |
| LY-01 | Day/night terminator | WM-34 | `[x]` **Done** — computed from the solar ephemeris, no data source and no licence. Verified across a full year |
| LY-02 | Military installations | WM-04 | `[x]` **Done** — 5,685 OpenStreetMap named military features, ODbL 1.0, source hash recorded |
| LY-03 | Nuclear power plants | WM-05 | `[x]` **Done** — 218 OSM plants tagged nuclear. **Scope changed:** irradiators are *not* in OSM, so this layer is plants only and says so |
| LY-04 | Chokepoints and strategic straits | WM-28 | `[!]` **Still blocked** — no canonical public dataset |
| LY-05 | Ports and terminal reference maps | WM-53 | `[x]` **Done** — Natural Earth 10m ports, public domain, source SHA256 recorded |
| LY-06 | Space launch facilities | WM-08 | `[x]` **Done** — 36 OSM spaceports, ODbL 1.0 |

**Four of the six reference layers now exist.** Chokepoints remain blocked: there is no canonical public
dataset for them, and hand-built passage geometry would be invented data.

**Shared work — the reference-layer substrate: `[x]` done**

- `src/reference-layers.js` — registry with class, basis, precision, publisher, licence, registry version and
  retrieval date per layer; explanation text for FR-WS-06.
- Layer registration in `src/map.js` beneath every evidence layer, so published context can never be read as a
  detected event; `setReferenceLayers()` and `referenceStatus()`.
- Reference layers excluded from `filters()` in `src/main.js`, so enabling one never changes which records the
  dashboard requests or counts.
- Panel treatment: separated rows, a `ref` badge instead of a record count, and an `i` control opening the
  sourcing panel.
- FR-LY-02 enforcement: geometry whose file does not declare the registry version this build expects is refused
  and the reason shown, never drawn as current.
- Tests: `tests/browser/reference-layers.spec.js`, 15 cases.

**Terminator geometry note.** The lit region spans more than 180° of longitude near a solstice, so it cannot be
one ring. `nightStrips()` emits it as latitude strips cut at absolute multiples of 180, which bounds every polygon
to half a turn and makes the output valid GeoJSON with no antimeridian case and no hole winding. Verified over
2,928 three-hourly samples in 2026: no misclassified point on either side, no coordinate outside ±180/±90, and
polar daylight/night landing on the correct pole.

**Acceptance:** a reference layer renders with its registry version and licence visible, is excluded from event
counts, and is refused if its registry version is unknown. **Met.**

---

## WM-P2 — Event layers: wiring existing evidence to the map

**Priority:** P1 · **Effort:** S–M per layer · **Depends on:** WM-P1.

Several catalog layers are largely built already and simply never drew. This phase is smaller than the registry
suggests.

| Item | Layer | Registry row | Existing evidence | Work |
| ---- | ----- | ------------ | ------------------ | ---- |
| LY-07 | Internet disruptions | WM-24 | `cyber_disruptions` already carried `measurement_from`, `measurement_until`, `method`, `datasource`, `score`, `uncertainty`, `original_url`; `cyber_ddos_series` holds the Radar aggregates | `[x]` **Done** — drawn at the country reference point, 9 retained observations visible. Protocol share is not an outage measurement |
| LY-08 | Protests | WM-17 | ACLED carries a protest event type | `[ ]` Next — promote out of generic events |
| LY-09 | Conflict areas | WM-03 | ACLED and GDELT conflict events | `[ ]` Curated area polygons beside the existing events |
| LY-10 | Multi-hazard | WM-26 | USGS earthquakes, FIRMS fires | `[ ]` Flood, cyclone, volcano and drought alongside, with deduplication and per-source severity retained |
| LY-11 | Hotspot concentration | WM-02 | `regional-anomalies` source, `src/country-ribbon.js` | `[ ]` Ranked hotspot surface |
| LY-12 | Displacement stocks and flows | WM-19 | — | `[ ]` **Counts and flows must not be mixed.** No existing source |

**Acceptance:** each layer states measurement basis, source time and coverage limits in its explanation surface, and
renders an explicit unknown state rather than dropping records.

---

## WM-P3 — Licensed live layers

**Priority:** P1/P2 · **Effort:** L per group · **Depends on:** WM-P0 decisions.
Directly serves the disruption-monitoring and country-research goals.

| Group | Layers | Registry rows | Notes |
| ----- | ------ | ------------- | ----- |
| Subsea and energy | Undersea cables, pipelines, storage facilities, fuel shortages | WM-10, 11, 56, 57 | Cables need a licensed versioned registry; reference routes are distinct from routes observed for a vessel |
| Navigation interference | GPS jamming | WM-31 | Only with a permitted dataset; show reporting window and measurement limits |
| Vessel traffic | Ship traffic, live tankers | WM-14, 58 | `backend/connectors/maritime.py` streams worldwide public AIS (OpenSeaFeed three-strip primary, Open Waters fallback) with course/speed tracking and rotating map glyphs. An AIS gap may reflect receiver coverage or equipment failure and must not be labelled sanctions evasion |
| Health and radiation | Disease outbreaks, radiation watch | WM-55, 07 | Disease news is not confirmed case totals; radiation variation is not a release |
| Climate | Climate anomalies | WM-20 | |

**Rules carried from the plan (§E, §I):** ship collection health, provenance, coverage and unknown states with every
layer. Do not enable a dataset merely because an adapter can be written. A facility location is not an attribution.

---

## WM-P4 — Saved research workspaces

**Priority:** P2 · **Effort:** L · **Depends on:** WM-P1.

The loop this enables: **open a saved watch → inspect what changed → review the evidence → save a finding → export a
briefing.**

| Item | Work | Plan source |
| ---- | ---- | ------------ |
| UX-01 | Mission presets (Cyber Research, Country Watch, Conflict Reporting) as task templates | Stage 1 |
| UX-02 | Named workspaces and tabs persisting their own filters and layout | Stage 1 |
| UX-06 | Shareable map state as a versioned, allowlist-only URL | Stage 1 |
| UX-07 | Named multi-country regional presets beside the existing `#country` filter | Stage 1 |
| UX-08 | Per-reader source preferences, separated from administrator collection enablement | Stage 1 |
| UX-18 | Versioned device/account preference persistence | Stage 1 |
| UX-17 | Layer explanation popovers: basis, units, freshness, limits | Stage 1 |
| UX-09 | Unread and recently-changed items with a stable per-reader cursor | Stage 1 |
| UX-10 / AL-01 | Persistent country/entity/keyword/source watches | Stage 1 |
| UX-11 | Multi-panel country dossier over existing endpoints | Stage 1 |
| UX-13 | Scoped dashboard CSV and printable evidence brief | Stage 1 |

**Implementation notes grounded in this repository**

- State lives in DOM controls (`#layers`, `#country`, `#period`, `#time-basis`, `#theme`, `#viewport-filter`) with a
  `sessionStorage`-backed partial state object and no `localStorage` anywhere. `UX-18` introduces the versioned
  preference store; the other items should read from it rather than from the DOM.
- The tab strip already exists (`#analysis-tab`, `#feed-tab`, `#military-tab`, `#sentiment-tab`); `UX-02` adds
  persistence and per-tab filter state rather than new tabs.
- `backend/advanced/watch.py` and the `watch_sources` / `webpage_snapshots` / `source_changes` tables already implement
  change detection. `UX-09`/`AL-01` reuse that revision model over `external_records` rather than adding a second.
- `saved_narrative_searches` (`backend/migrations/004_advanced.sql:67`) is the precedent for a named saved object.
- `UX-06` must be an allowlist: credentials, private queries and case identifiers never enter the URL.

**Acceptance (plan §H):** saved workspace, shareable map, personal source filters, change tracking, watchlist and
country dossier rows all pass; a new revision appears once as changed and refresh alone creates no unread item; zero
matches are shown distinctly from collection failure.

---

## WM-P5 — Scheduled briefings and one delivery channel

**Priority:** P2 · **Effort:** L · **Depends on:** WM-P4.

| Item | Work | Plan source |
| ---- | ---- | ------------ |
| AI-11 | Editorial rules: deduplicate by source family; distinguish commentary, updates, durable events | Stage 2 |
| AI-01 | Brief composed from an explicit evidence window and the reader's watches | Stage 2 |
| AI-05 | Reviewed editions with explicit publish/revoke, private by default | Stage 2 |
| AL-02 | Event and threshold rules with a match preview before enabling | Stage 2 |
| AL-03 | Timezone-aware scheduled editions, first as an in-app inbox | Stage 2 |
| AL-04 | One delivery channel with explicit recipient opt-in | Stage 2 |
| AL-07 | Quiet hours and per-channel routing with test preview | Stage 2 |
| AL-08 | Outbox, retries, deduplication keys, expiry, delivery audit | Stage 2 |

Reuse the worker leases and persisted `investigation_jobs`, but create notification-specific tables. Ground editions in
the existing citation-ID checks and labelled-draft pattern (`backend/ai_output.py`). Source-family duplicates must not
count as corroboration.

---

## WM-P6 — Identity and tenancy — gate before the first paid customer

**Priority:** P0 **at sale time**, P3 until then · **Effort:** L / XL.
Demoted from a feature prerequisite. Today one shared administrator token (`OSINT_ADMIN_TOKEN`, used by
`backend/main.py` `Depends(authorize)` and `backend/advanced/api.py:75`) is the only access control, which is
acceptable for a single-operator research installation and unacceptable for a shared one.

| Item | Work | Plan source |
| ---- | ---- | ------------ |
| SAAS-01 | Individual identities and sessions | §D |
| SAAS-03 | Organizations, member roles and owned evidence | §D |
| SAAS-04 | Explicit account-deletion policy; soft-deleted cases are not erasure | §D |
| SAAS-05 | Atomic per-customer quotas and usage display | §D |
| DEV-03 | Named, expiring, revocable scoped credentials | §D |
| TEN-01 | Scope every private query in `investigation_cases`, `case_evidence`, `case_notes`, `media_evidence`, `investigation_jobs`, `advanced_provider_cache` and export paths by organization | §D, §H |

**Acceptance (plan §H "Customer isolation"):** a second account cannot enumerate another account's cases, evidence
files, jobs, exports, caches or delivery destinations.

**Why it stays on the board:** §D states that billing alone does not provide isolation. This cannot be retrofitted
cheaply once private customer records exist, so it must be scheduled against the sales decision rather than
discarded.

---

## WM-P7 — Platform access and optional specialisation

**Priority:** P3 · **Effort:** M–XL. Not a roadmap commitment.

| Group | Items | Plan/catalog rows |
| ----- | ----- | ----------------- |
| Developer access | Documented API contract, read-only MCP tools, agent discovery, embeddable public-safe surfaces | DEV-01, 02, 05, 06 |
| Commercial | Billing, enterprise restore/update/support contracts | SAAS-02, SAAS-06 |
| Analysis | Optional embeddings, multilingual analysis, source-quality dimensions | AI-07, 08, 10 |
| Interface | Panel reorder/resize, map/feed presets, workspace snapshots, text size, mobile guidance, multilingual UI, city geocoder | UX-03, 04, 12, 14, 15, 16, 25, 26 |
| Markets | Watchlists, macro tiles, calendars, rates, commodities — licensing and quote-delay semantics are separate work | FIN-01…FIN-38 |
| Country scores | CII, CRI, five-factor scorecard, demographics, food stocks, financial exposure | GEO-02…GEO-07 |
| Routes and scenarios | Route explorer, scenario engine, supply-chain graph | FLOW-01…FLOW-11 |
| China program | Disclosures, release calendar, vintage history, corridors, decision signals | CHN-01…CHN-12 |
| Defence geography | Surge detection, presence detection, naval heuristics, posture cards | MIL-03…MIL-12, 17…MIL-19 |
| Convergence | Cross-source agreement, hubs, social velocity, GDELT, prediction markets, PizzINT | GEO-13…GEO-22 |
| Renderer and packaging | 3D globe, live streams, webcams, native desktop, offline AI, WebMCP | UX-21…UX-24, 28, DEV-07…09 |
| Conversational AI | Bounded analyst conversation, validated navigation actions | AI-03, AI-04 |

**Rule:** a `P3` item does not enter a phase until it has a customer, a permitted source and an evaluation method.

---

## Layer inventory

All 58 registry entries with Signal Atlas anchors. `WM-xx` is the catalog's `MAP-xx` row.

| WM | Registry layer | State | Signal Atlas anchor / gap | Phase |
| -- | -------------- | ----- | ------------------------ | ----- |
| 01 | Iran Attacks | Absent | `backend/connectors/conflict_sources.py` carries country coverage, not this layer | P3 |
| 02 | Intel Hotspots | Partial | `regional-anomalies`, `src/country-ribbon.js`; no ranked hotspot surface | **P2** |
| 03 | Conflict Zones | Partial | ACLED/GDELT conflict events; no curated area polygons | **P2** |
| 04 | Military Bases | **Present** | 5,685 OSM named military features (LY-02) | **P1 done** |
| 05 | Nuclear Sites | **Present** | 218 OSM nuclear **power plants** (LY-03); not an irradiator or regulator list | **P1 done** |
| 06 | Gamma Irradiators | Absent | Not present in OpenStreetMap; no verified source | Blocked |
| 07 | Radiation Watch | Absent | — | P3 |
| 08 | Spaceports | **Present** | 36 OSM spaceports (LY-06) | **P1 done** |
| 09 | Orbital Surveillance | **Present** | `orbital-positions`, `orbital-tracks`, `backend/orbital_catalog.py` | — |
| 10 | Undersea Cables | Absent | — | P3 |
| 11 | Pipelines | Absent | — | P3 |
| 12 | AI Data Centers | Absent | — | Skip |
| 13 | Military Activity | **Present** | Military category + aircraft military flag | — |
| 14 | Ship Traffic | **Present** | `backend/connectors/maritime.py` worldwide public AIS + rotating course/speed glyphs | — |
| 15 | Trade Routes | Absent | — | P3 |
| 16 | Aviation | **Present** | `aircraft`, `aircraft-trail`; OpenSky live interpolation | — |
| 17 | Protests | Partial | ACLED protest type renders as generic events | **P2** |
| 18 | Armed Conflict Events | **Present** | ACLED + GDELT | — |
| 19 | Displacement Flows | Absent | — | **P2** |
| 20 | Climate Anomalies | Absent | — | P3 |
| 21 | Severe Weather Alerts | Absent | USGS quakes + FIRMS fires only | **P2** |
| 22 | Canada Roads | Absent | — | P7 |
| 23 | Canada Alerts | Absent | — | P7 |
| 24 | Internet Disruptions | **Present** | `cyber_disruptions` drawn at the country reference point (LY-07); 9 retained observations | **P2 done** |
| 25 | Cyber Threats | **Present** | `cyber-network`, `threat-network`, `cyber_observations` | — |
| 26 | Natural Events | Partial | Earthquakes and fires; no multi-hazard aggregation | **P2** |
| 27 | Fires | **Present** | FIRMS | — |
| 28 | Chokepoints | Absent | No canonical public dataset; hand-built geometry would be invented | Blocked |
| 29 | Economic Centers | Absent | — | Skip |
| 30 | Critical Minerals | Absent | — | Skip |
| 31 | GPS Jamming | Absent | — | P3 |
| 32 | Country Instability | Absent | **Declined.** Plan §E forbids relabelling reporting volume as validated risk | — |
| 33 | Resilience | Absent | **Declined.** Heuristic country score | — |
| 34 | Day/Night | Absent | Solar terminator; computed locally, no data source | **P1 done** |
| 35 | Sanctions | Partial | `backend/connectors/ofac.py` guidance RSS; no designations list/version/entity model | P3 |
| 36 | Startup Hubs | Absent | — | Skip |
| 37 | Tech HQs | Absent | — | Skip |
| 38 | Accelerators | Absent | — | Skip |
| 39 | Cloud Regions | Absent | — | Skip |
| 40 | Tech Events | Absent | — | Skip |
| 41 | Stock Exchanges | Absent | — | Skip |
| 42 | Financial Centers | Absent | — | Skip |
| 43 | Central Banks | Absent | ECB is one RSS feed (`backend/connectors/registry.py:48`), not a layer | Skip |
| 44 | Commodity Hubs | Absent | — | Skip |
| 45 | GCC Investments | Absent | — | Skip |
| 46 | Positive Events | Absent | Audience variant | P7 |
| 47 | Acts of Kindness | Absent | Audience variant | P7 |
| 48 | World Happiness | Absent | Audience variant | P7 |
| 49 | Species Recovery | Absent | Audience variant | P7 |
| 50 | Clean Energy | Absent | Audience variant | P7 |
| 51 | Mining Sites | Absent | — | Skip |
| 52 | Processing Plants | Absent | — | Skip |
| 53 | Commodity Ports | Absent | **Live** as `ports` (WM-P1, Natural Earth 10m, public domain) | **P1 done** |
| 54 | Live Webcams | Absent | — | P7 |
| 55 | Disease Outbreaks | Absent | — | P3 |
| 56 | Storage Facilities | Absent | — | P3 |
| 57 | Fuel Shortages | Absent | — | P3 |
| 58 | Live Tanker Positions | Absent | Subtype of AIS; no default feed | P3 |

**Skip rationale.** The tech and finance geography clusters (WM-12, 29, 30, 36–45, 51, 52) require licensed commercial
datasets and serve no task in the three stated monitoring domains.

---

## Preserved without change (plan §F)

Map clustering, layer topic search, UTC periods, geographic filters, live aircraft interpolation, orbital propagation,
source health, bounded collection, sentiment samples, threat catalogs, typed infrastructure evidence, local indexed
search, cases, notes, relationship graphs and citation-checked AI analyses.

---

## Open decisions

From plan §J. Questions 1, 3 and 5 are now partly answered and marked accordingly.

| # | Question | State |
| - | -------- | ----- |
| 1 | Which customer task is the first paid pilot? | **Answered:** all three — cyber, country research, disruption |
| 2 | Which sources permit commercial display, storage, exports and alerts? | Open. Blocks WM-P3 and WM-P0 LIC-04 |
| 3 | Isolated installation or shared SaaS? | Open, but not urgent. Deferred to WM-P6 |
| 4 | Which delivery channel and cadence do users need? | Open. Blocks WM-P5 |
| 5 | What false-positive rate is acceptable per alert or score? | Open. Blocks WM-P5 and WM-P7 scores |

---

## Phase log

Append one entry per completed phase: date, items closed, verification commands run, evidence artefacts, and anything
deliberately left open.

### 2026-10-17 — WM-P1: distinct pictograms for every reference layer

All reference points were drawn as identical slate circles, so Military Installations and Nuclear Power Plants were
indistinguishable on the map. Each layer now has its own pictogram, and the military layer separates naval from air
facilities within itself.

| Layer | Pictogram | Colour |
| ----- | --------- | ------ |
| Military installations | Shield with chevron | slate `#9fb3c2` |
| — naval base | same shield | teal `#8dc7da` |
| — air base / aerodrome / airfield | same shield | amber `#e5b06a` |
| Nuclear power plants | Radiation trefoil | amber `#f0c05a` |
| Space launch facilities | Rocket | lilac `#c6bcff` |
| Ports and terminals | Anchor | teal `#8dc7da` |
| Day/night terminator | Half-lit disc | slate `#5f7280` |

Shape separates the layer; colour separates subtypes inside it, because "naval or air?" is the question an analyst
actually asks of a military layer. The military layer selects its icon with a `match` on `facility_type`, so one
source layer yields three pictograms.

**Dots below zoom 3, pictograms above it.** With 5,685 military points, pictograms at world scale would be
unreadable, and below zoom 3 they crowd out the evidence layers they sit beneath. The circle layer is now capped at
zoom 3 and the symbol layer starts there, with `icon-allow-overlap` and `icon-ignore-placement` so reference geometry
never displaces recorded events. The halo circle is unchanged and keeps the pointer target reachable at every zoom.

**The same pictograms are used in the layer panel and the map key**, so the legend and the map agree.

**Four bugs found by testing rather than by looking:**

1. **Ports drew a military shield.** `referenceIconExpression` derived the icon from the layer id by trimming a
   trailing `s`, so `ports` missed `REFERENCE_IMAGE_NAMES.port` and fell through to the military default. Replaced
   with an explicit `REFERENCE_ICON_BY_LAYER` table keyed by layer id.
2. **A temporal dead zone broke the whole map.** The icon table was declared *inside* the style load handler, after the
   call site, so the first render threw and the map never became ready. Caught because the test waited for
   `dataset.ready` instead of assuming it.
3. **Pictograms were registered after `ready`**, so the map could report itself ready while its symbol layers pointed
   at images the style did not hold. Registration now happens before `ready` is set.
4. **A removal deleted too much.** An over-eager block delete took out the reference hover handlers along with the
   image registration; caught by rebuilding and re-reading the file rather than trusting the edit.

**Testing icon rendering needed a deterministic camera.** Zooming blindly landed in empty ocean, where "no icons" is
indistinguishable from "icons broken". The map already publishes a projected reference point, so the test now drags
that exact feature to the centre of the canvas and zooms on it: **7,019 dots at world zoom, 48 pictograms zoomed in,
dots at zero.** One icon-hover test was written and then deleted — it duplicated hover coverage already in
`reference-layers.spec.js` and was flaky, and a suite that cannot be trusted is worse than a gap.

**Verification.** `tests/browser/reference-icons.spec.js`, 3 cases: distinct panel pictograms, six pictograms
registered with each layer selecting its own, and the dot-to-pictogram threshold. `pytest tests/backend` —
**286 passed**. Full browser suite — **55 passed, 3 failed, 1 skipped**; all three failures are the pre-existing
`dashboard.spec.js` set. `ruff` and `prettier` clean on every file touched.

### 2026-10-17 — WM-P1 completed: OpenStreetMap reference layers (LY-02, LY-03, LY-06)

Owner accepted ODbL 1.0. Three layers built from OpenStreetMap via the Overpass API by
`scripts/build_reference_osm.py`, which is checked in so the result is reproducible.

| Layer | Registry | Features | Licence |
| ----- | -------- | -------- | ------- |
| Military installations (LY-02) | OSM `military=naval_base\|air_base\|aerodrome\|airfield\|base` with a name | 5,685 | ODbL 1.0 |
| Nuclear power plants (LY-03) | OSM `power=plant` tagged nuclear | 218 | ODbL 1.0 |
| Space launch facilities (LY-06) | OSM `aeroway=spaceport` with a name | 36 | ODbL 1.0 |

Every coordinate comes from a recorded Overpass response; the response hash, the exact query, the publisher,
the licence and the retrieval date are written into each file and shown in the layer's explanation panel and on
every feature's hover card. Attribution and the share-alike obligation are recorded in
`public/reference/REFERENCE_LICENSES.txt`.

**Counts independently confirmed.** An `out count` query returned 5,712 military, 518 nuclear and 36 spaceport
features. The extraction returned 5,685 and 218 — lower because 27 co-mapped duplicates collapsed and the
nuclear query changed to facility level. Nothing was lost.

**Three things found by checking rather than assuming:**

1. **Guessed tags returned nothing.** `aeroway=spaceport` and `military=air_base` both came back empty. Probing
   the vocabulary showed spaceports are mapped as *areas*, not nodes, so they need `nwr` and a centroid. Nothing
   would have shipped had I trusted the first guess.
2. **The nuclear layer was listing reactor units, not plants.** `generator:source=nuclear` returned 518 entries
   including `(TAPS)-3` and `(TAPS)-4` — individual units of one Tarapur station. Presenting those as
   "facilities" would have been wrong. Switching to facility-level `power=plant` tagging gives 218 real plants:
   Akkuyu, Calvert Cliffs, Laguna Verde.
3. **Overpass mirrors are fragile.** The global military query succeeded on some attempts and 502'd on others,
   and a banded fallback I added failed twice — once from a real syntax bug and once from hammering struggling
   public mirrors. The fallback was removed rather than debugged: a crawl that fails on some regions would
   silently produce a registry that looks complete and is not, which is worse than not shipping the layer.

**Irradiators are not in OpenStreetMap.** `man_made=irradiator` and a bare `irradiator` tag both return nothing.
LY-03 is therefore scoped and labelled as nuclear *power plants* only, and the irradiator registry (WM-06) stays
blocked rather than being folded into the plant layer under a misleading name.

**Chokepoints remain blocked.** No canonical public dataset exists, and hand-built passage geometry would be
invented data. Recorded as blocked in the layer inventory.

**Verification.** `tests/browser/reference-layers.spec.js` grew to 26 cases, adding a group per OSM layer
(registry version match, attribution on every feature, no invented coordinates, panel and explanation state), a
facility-level guard on the nuclear layer, and a hover-card check asserting the publisher and ODbL licence are on
the card. Live check in the browser: all four OSM layers load with no console errors, and a military feature's card
reads *Ataq international Airport — YE, airfield, OpenStreetMap contributors 2026-10, ODbL 1.0*.
`pytest tests/backend` — **286 passed**. Full browser suite — **50 passed, 5 failed, 1 skipped**; all five
failures are in `dashboard.spec.js` / `infrastructure-layer.spec.js` and reproduce on a stashed tree.
`ruff` and `prettier` clean on every file touched.

### 2026-10-17 — WM-P2: reference-layer panel and map hover cards fixed and finished

Reported from the running app: the `i` controls on reference rows floated detached from their labels, and reference
points gave no hover summary.

| Defect | Cause | Fix |
| ------ | ----- | --- |
| `i` button 34px tall instead of 17 | No `box-sizing: border-box`, so the border was added outside the declared height | `box-sizing: border-box`, `padding: 0`, `min-height: 0`, `align-self: center` |
| `i` and count floated mid-row | The limitation note wrapped to 4–5 lines inside `.layer-copy`, making rows 103–142px tall, and the controls centred in all of it | Note moved out of `.layer-copy` onto its own line, clamped to 2 lines, with a short `summary` per layer instead of deriving one from the first sentence of `limitation` |
| Button wrapped to line 2 | `.layer-copy` was not shrinkable, so a long label pushed the count and button past the row | `.layer-copy` shrinkable with `min-width: 0`; the label truncates with an ellipsis, and `Ports and maritime terminals` shortened to `Ports and terminals` so it does not need to |
| Note overflowed the row | `flex: 0 0 100%` plus a 25px indent exceeds the row width | `flex: 0 0 calc(100% - 25px)` |
| `REF` badge jammed against the note text | It followed the text, so the spacing belonged on its left | `margin-left` |
| Availability styling and `data-count` lost | Moving the badge created a new element and dropped the hook `applyReferenceLayers()` looks up | The same count element is reused with the `layer-count-reference` class, keeping `data-count` |

**Hover cards added for both layer kinds.** Reference points and disruption observations now answer `mousemove`
with the same card structure the report and aircraft cards use (`hover-kind`, `strong`, `orbital-hover-card`,
`hover-location`, provider link), rather than the ad-hoc classes I first invented — `event-hover-title` and
`disruption-fields` did not exist in this stylesheet, which is why the port name never appeared in the card.

A port's card reads: name, country where the boundary test resolved it, source and registry version, licence, the
layer's stated limit, and a link to the licence terms. It opens with **"Reference location · not an observation"**.

**Reference points now grow with zoom** (3.5px at world view to 8px at z12, halo 7 to 16). At 2.6px they were not a
reachable pointer target, which is why the first hover test could not find one by sweeping.

**Two test-methodology errors of my own.** The hover test swept the canvas on a 40px grid and timed out: blind
sweeping is slow and flaky. It now reads a projected point from the same `data-*` instrumentation the map already
publishes for tests. Two "no refetch" tests were also failing intermittently because background refresh timers and a
rate-limited API made request counting timing dependent; both now stub every endpoint, so the only requests that can
occur are the ones the test causes.

**Verification.** `tests/browser/reference-panel.spec.js`, 3 new cases (row alignment, hover card contents, zoom
growth). `pytest tests/backend` — **286 passed**. Full browser suite — **39 passed, 5 failed, 1 skipped**; all five
failures are in `dashboard.spec.js`, which reproduces on a stashed tree. `ruff` and `prettier` clean on every file
touched; the only remaining lint findings are pre-existing ones in files this work did not touch.

### 2026-10-17 — WM-P2 started: internet-disruption observations drawn (LY-07)

**Closed:** LY-07.

The `cyber_disruptions` evidence had been collected, stored and displayed in the investigation workspace since
WM-P0's era, but had never been drawn on the map. It now is.

| Decision | Choice and reason |
| -------- | ----------------- |
| Where the marker goes | The country reference point from `public/countries.geojson`, the same resolution the rest of the product uses. The provider returns country aggregates, so any more precise placement would be invented |
| Marker size | Rank within the response, not the raw score. The score is a provider median in its own units, so comparing a `bgp` row against a `ping-slash24` row by magnitude would be meaningless |
| Credential | The evidence API needs the operator token, so the layer states that plainly instead of showing an empty map. Four distinct states: no credential, refused, empty, failed |
| Unresolvable country | Reported as unplaced. One retained row (US Virgin Islands) is outside `countries.geojson` and is counted, not guessed onto a neighbour |
| Provenance on the card | Method, datasource, both windows, uncertainty, retrieval time and the provider's original URL. `uncertainty` is `null` here and is shown as "Not supplied by the provider" rather than as a value |

**Two placement bugs, both from editing at the wrong anchor.** The source and layer registrations were first written
inside `setReferenceLayers()` because the text I anchored on (`referenceVisibility();`) appears in two places. A
later removal deleted the *correct* copy in the load handler instead of the misplaced one, which is how the layers
ended up registered on every layer change but never at startup. The app surfaced this itself:
`The layer 'disruptions-point' does not exist in the map's style`. Anchoring on a multi-line unique block, and
verifying with `rg` before removing, is the fix.

**One measurement of my own was wrong.** My first canvas instrumentation reported `disruptionsDrawn: 0` because
`samples()` in `sampleCanvas` filters a pre-built `byLayer` map that only covers a fixed list of layers. The layer
was not failing to draw; the instrument was not looking. Adding the layer to the query list gave 9 drawn, matching
9 loaded.

**Verification.** `tests/browser/disruptions.spec.js`, 11 cases, including one that toggles the layer and asserts
**zero** `/api/` record queries — the invariant that reference and evidence-API layers never change which events the
dashboard asks for. Live check against retained evidence: 9 loaded, 9 drawn, no console errors.
`pytest tests/backend` — **286 passed**. Full browser suite — **37 passed, 4 failed, 1 skipped**; all four failures
are in `dashboard.spec.js` and reproduce on a stashed tree. `ruff` and `prettier` clean on every file touched.

**Note on tooling.** The vite dev server died during this phase. Rather than starting one, verification ran through
the repository's own Playwright harness, which manages its web server with `reuseExistingServer`. That is the
projected workflow and it needs no manual server lifecycle.

### 2026-10-16 — WM-P1 started: reference-layer substrate, terminator and ports

**Closed:** the WM-P1 substrate, LY-01, LY-05. **Blocked:** LY-02, LY-03, LY-04, LY-06.

| Item | State | Evidence |
| ---- | ----- | -------- |
| Substrate | Done | `src/reference-layers.js`; registration and status in `src/map.js`; panel and filtering in `src/main.js`, `src/layer-symbols.js`, `src/style.css` |
| LY-01 terminator | Done | Computed; `nightStrips()` + `terminatorLines()`; 2,928-sample year verification |
| LY-05 ports | Done | `scripts/build_reference_ports.py` → `public/reference/ports.geojson`, 1,081 Natural Earth points, source SHA256 `c5a5028f…`, terms in `public/reference/REFERENCE_LICENSES.txt` |
| LY-02/03/04/06 | Blocked | No verified source; see below |

**Near-miss worth recording.** LY-02 was first written as a hand-entered list of ~45 military base coordinates
recalled from memory and stamped "OpenStreetMap / ODbL". That is fabricated data carrying a false provenance
label, and it violates the no-fabricated-data rule in `BUILD_CONTRACT.md` as squarely as inventing a satellite
position would. It was deleted before it reached the map. `public/reference/` now contains only geometry whose
upstream bytes were downloaded and hashed, and the extraction script is checked in so the result is reproducible.
**A reference layer with no verified source is left unimplemented, not approximated.**

**Natural Earth property names were guessed wrong first.** The first extraction run produced 0 ports because the
script assumed `label_x`/`label_y`; the real schema publishes ports as `Point` geometry with only
`name`/`featurecla`. Re-read the source rather than trusting the guess.

**Two real geometry bugs, both found by testing rather than by looking.** The subsolar longitude was computed as
`-(GMST + RA)` instead of `RA - GMST`, which put the sun's own meridian 180° out at the solstice. And the
terminator ring had a 360° discontinuity where the two branches meet, because they coincide only modulo a full
turn — which produced a polygon that looked plausible on screen and was wrong. Both were caught by asserting the
subsolar point is lit and the antisolar point is dark, rather than by inspecting the picture.

**One bug caught by the app itself.** `referenceLoaded` was referenced where the map holds `referenceLoading`,
throwing a ReferenceError that broke the dashboard. The new browser test caught it on first run.

**Verification.** `pytest tests/backend` — **286 passed**. `npx playwright test tests/browser/reference-layers.spec.js`
— **15 passed**. Full browser suite — **27 passed, 3 failed, 1 skipped**; all three failures are in
`dashboard.spec.js` and reproduce identically on a stashed working tree, so they are pre-existing and flaky rather
than regressions (baseline stashed run: 4 failed, 7 passed in that file). `ruff` and `prettier` clean on every file
touched.

### 2026-10-16 — WM-P0 implemented; live layer audit; backlog re-ordered to features-first

**Closed:** LIC-01, LIC-02. **Open:** LIC-03, LIC-04.

| Item | State | Evidence |
| ---- | ----- | -------- |
| LIC-01 `source_permissions` table | Done | `backend/migrations/009_source_permissions.sql`; re-entrant (`IF NOT EXISTS` / `INSERT OR IGNORE`) so rewinding `user_version` cannot brick a database |
| LIC-02 collector gate | Done | `permission_refusal()` in `backend/worker.py`; `state="permission_required"` with the refusal reason on `connector_status` |
| LIC-03 `docs/SOURCES.md` column | Open | not yet written |
| LIC-04 pilot decision record | Open | owner decision |

**Design decision recorded.** The gate engages only when `OSINT_COMMERCIAL_USE=true` (`Settings.commercial_use`,
`backend/config.py`). Without it the product behaves exactly as before. With it, any source whose decision is not
`cleared` is refused. The three sources named in plan §I are seeded `review_required`, not `blocked` — the plan
identifies them as needing *review*, and blocking would have broken working collection on a review question rather
than a prohibition.

**Live audit.** Confirmed against the running application (vite 5173, API 8000), not just source reading. The layer
panel offers exactly 10 toggles — geopolitical, military, aviation, maritime, sentiment, cyber, infrastructure,
economic, environment, space — all record-derived. 147/186 sources current, 4,265 matching records, 441 mapped, no
console errors. Screenshot `layers-before.png`. This confirms the WM-P1 premise: zero static reference layers.

**Re-order rationale.** Owner priorities recorded above. Identity and tenancy moved from phase 1 to WM-P6 because no
customer shares the installation yet; it stays on the board as a pre-sale gate.

**Regressions fixed while landing WM-P0.** `set_permission(**model_dump(), …)` raised `TypeError` from a duplicate
keyword; `sources.license` was read instead of `license_classification`; and the register was wrongly described as
public when the whole `/api/v1` router sits behind `read_access`. Two tests hardcoded the schema version and now
derive it from the migration files.

**Verification.** `pytest tests/backend` — **286 passed**. `ruff check` and `ruff format` clean on all touched files.
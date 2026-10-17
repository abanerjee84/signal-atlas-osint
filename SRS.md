# Signal Atlas Research Workspace SRS

**Document ID:** OSINT-SRS-002
**Version:** 1.7
**Status:** Development baseline
**Supersedes:** nothing. **Complements:** `BUILD_CONTRACT.md` (OSINT-SRS-001, platform baseline), `ADVANCED_OSINT_SPEC.md` (AOS-01…AOS-11, advanced modules)
**Inputs:** [`docs/WORLDMONITOR_INCORPORATION_PLAN.md`](docs/WORLDMONITOR_INCORPORATION_PLAN.md), [`docs/WORLDMONITOR_FEATURE_CATALOG.md`](docs/WORLDMONITOR_FEATURE_CATALOG.md), [`docs/TODO.md`](docs/TODO.md)
**Target platform:** Ubuntu Linux server, 8 GB RAM, SQLite/WAL, FastAPI, Vite frontend

**Changelog**

| Version | Date | Change |
| ------- | ---- | ------ |
| 1.0 | 2026-10-16 | Initial requirements derived from the incorporation plan |
| 1.1 | 2026-10-16 | Added §10 FR-LY-01…06 (map layer classes, reference geometry provenance, declined layers), AC-12/AC-13, and the layer coverage baseline in §13, following the layer gap analysis |
| 1.2 | 2026-10-16 | Added §10 FR-LY-01…06 (map layer classes, reference geometry provenance, declined layers), AC-12/AC-13, and the layer coverage baseline in §13, following the layer gap analysis |
| 1.3 | 2026-10-16 | WM-P1 landed the reference-layer substrate with two layers (terminator, ports). Added FR-LY-07: a reference layer with no verified source is left unimplemented rather than approximated. Updated the coverage baseline |
| 1.4 | 2026-10-17 | WM-P2 drew the retained internet-disruption observations (LY-07). Added FR-DM-06 governing country-aggregate measurements, and FR-LY-08 covering layers sourced outside the dashboard's own record query |
| 1.5 | 2026-10-17 | Added FR-LY-09: every reference and evidence-API layer must answer hover with a card using the product's established hover structure, and reference points must remain reachable pointer targets at every zoom |
| 1.6 | 2026-10-17 | WM-P1 completed with four OpenStreetMap reference layers. Added FR-LY-10 on share-alike attribution and FR-LY-11 requiring facility-level, not component-level, registry entries |
| 1.7 | 2026-10-17 | Added FR-LY-12: reference layers carry distinct pictograms, selected per layer and per facility subtype, and reference geometry must never displace recorded events |

---

## 1. Purpose and scope

This document specifies the requirements that turn Signal Atlas from a live dashboard into a **repeatable research
product**: an analyst opens a saved workspace, sees what changed since they last looked, reviews the underlying
evidence, records a finding, and exports or schedules a briefing.

It is written from the World Monitor incorporation plan, which assessed that product on 15 October 2026 and recommended
building saved workspaces, watchlists, change tracking, evidence-based country dossiers and scheduled briefings first,
adding a small number of commercially permitted infrastructure datasets next, and keeping financial tooling, predictive
country scores and a new 3D engine as optional later projects.

### 1.1 In scope

Persistence and sharing of analyst workspace state; per-reader preferences and review cursors; watches over retained
evidence; a consolidated country dossier; scoped export; editorial briefings; one delivery channel; identity, tenancy
and isolation; developer access; and a gated set of additional map layers and domain data feeds.

The map layer work is specified separately because a layer-gap analysis against this product's actual 23 map sources
found that the dominant absence is not individual feeds but the absence of any static reference layer at all. See
§5 (FR-LY-01…06) and the 58-row inventory in [`docs/TODO.md`](docs/TODO.md).

### 1.2 Out of scope

Any copy of World Monitor source, data, branding or hosted API output. Its platform licence is AGPL-3.0-only with separate
MIT client packages, and its upstream data rights are independent of its implementation; neither is granted by this
document. Also out of scope: predictive country risk scores and scenario impact models without a validated method (§11.6),
any payment or subscription action, and any change to the capabilities listed as preserved in plan §F.

### 1.3 Relationship to existing specifications

| Spec | Remains authoritative for |
| ---- | -------------------------- |
| `BUILD_CONTRACT.md` (OSINT-SRS-001) | Technology stack, connector independence, common event schema, deduplication, retention, AI quota control, base non-functional requirements, agent execution contract |
| `ADVANCED_OSINT_SPEC.md` (AOS) | Search and resource registry, cyber/infrastructure intelligence, social and narrative intelligence, geospatial and satellite investigation, media verification, entity relationships, website/source change monitoring, document intelligence, cross-domain AI correlation, case and evidence management, source validation |
| **This document (OSINT-SRS-002)** | Workspace persistence and sharing, personal preference and review state, watches, dossier, export, briefings, delivery, identity/tenancy, developer access, additional domain feed admission |

Where this document adds requirements, it does not relax OSINT-SRS-001. All identifiers, provenance fields, retention
behaviour and error-handling rules in that document continue to apply.

---

## 2. Design principles

1. **Evidence over resemblance.** Reusing a feature name or a visual confidence treatment is not evidence of an
   equivalent capability. Requirements below name the observable condition, not the upstream feature.
2. **Provenance stays visible.** Source identity, units, observation time, retrieval time, geographic precision, model
   version, missingness and correction history are shown next to the claim they support.
3. **Collection is not publication.** Per-reader filtering must never disable collection for other readers, and a
   configured connector must never imply a commercial right to display or redistribute its data.
4. **Modelled values stay labelled.** Scores, composites, nowcasts and scenario outputs declare their inputs, version and
   limitations. Reporting volume is not risk. Measured values and modelled values are never merged.
5. **Private stays private.** Public share links, exports and briefings carry an explicit allowlist. Absence from an
   allowlist is a denial, not an oversight.
6. **Degrade visibly.** Unknown, stale, zero-result and collection-failed states are distinct and each is renderable.

---

## 3. Terminology

| Term | Meaning in this document |
| ---- | ------------------------ |
| Event layer | A map layer derived from collected, georeferenced records; decays with its feed |
| Reference layer | A map layer derived from versioned static asset geometry; changes only when the registry is revised |
| Registry version | The version of the published asset registry a reference layer was built from |
| Workspace | A named, persisted set of layers, filters, time basis and layout |
| Reader | An authenticated identity with its own preferences, watches and review cursor |
| Collection enablement | Administrator-controlled decision to run a connector |
| Feed enablement | Reader-controlled decision to display a collector's output |
| Watch | A persisted predicate over retained evidence (country, entity, keyword, source) |
| Review cursor | A reader's last-reviewed revision marker for a watch or feed |
| Edition | A generated, dated briefing over an explicit evidence window |
| Delivery | Outbound notification of an edition or rule match to an opted-in recipient |
| Tenancy | The organization scope that owns cases, evidence, jobs, exports and caches |

---

## 4. Data model additions

Migrations are numbered SQL files in `backend/migrations/`, applied in order by `Database.initialize()` under
`PRAGMA user_version` (`backend/database.py:48`). The next migration number is **009**.

### FR-DATA-01 — Source permission register

Table `source_permissions` keyed by `source_id`. Columns: `display_class` (`public` / `attribution` / `restricted` /
`review_required`), `retention_allowed`, `export_allowed`, `derivative_allowed`, `basis` (free text), `reviewed_at`,
`reviewer`, `blocking`. A connector whose row is missing or whose `blocking` flag is set must not start collection and
must record a named reason in `connector_status`.

### FR-DATA-02 — Workspaces

Table `workspaces`: `workspace_id` (PK), `organization_id`, `owner_principal`, `name`, `kind` (`template` / `workspace`),
`state` (JSON: layers, country filter, regions, period, time basis, viewport, panel layout, feed enablement),
`state_version` (integer), `is_public_template`, `created_at`, `updated_at`, `deleted_at`. Unique on
`(organization_id, name)` among non-deleted rows. State is validated against a documented schema on write; unknown keys
are rejected rather than discarded, and a state whose `state_version` is newer than the application is refused.

### FR-DATA-03 — Regions

Table `regions`: `region_id` (PK), `organization_id`, `name`, `country_codes` (JSON array of ISO-3166 alpha-2),
`viewport` (JSON), `created_at`, `updated_at`. Regions are references, not filters on stored evidence.

### FR-DATA-04 — Reader preferences

Table `reader_preferences`: `(principal, key)` PK, `value` (JSON), `updated_at`. Preference documents carry a
`schema_version`. A document from a newer version is not applied; a document from an older version is migrated or
reset to defaults, and the reset is reported rather than silently swallowed. Device-local preferences are stored under a
separate namespace and are not merged into account preferences without an explicit user action.

### FR-DATA-05 — Watches

Table `watches`: `watch_id` (PK), `organization_id`, `owner_principal`, `name`, `countries` (JSON), `entity_ids` (JSON),
`keywords` (JSON), `source_ids` (JSON), `categories` (JSON), `min_severity`, `enabled`, `created_at`, `updated_at`.
Table `watch_matches`: `match_id` (PK), `watch_id`, `record_id` (FK `external_records`), `revision` (hash of the matched
record at match time), `reason` (JSON: which clause matched), `matched_at`, `acknowledged_at`. Unique on
`(watch_id, record_id, revision)` so a re-run does not duplicate an existing match.

### FR-DATA-06 — Review cursors

Table `review_cursors`: `(principal, scope)` PK where `scope` is a feed id or watch id, `last_reviewed_revision`,
`last_reviewed_at`. A cursor advances only when a reader explicitly marks items reviewed. Re-running collection, or
refreshing the page, must not advance a cursor.

### FR-DATA-07 — Editions and delivery

Table `briefing_editions`: `edition_id` (PK), `organization_id`, `created_by`, `window_from`, `window_to`, `sources` (JSON),
`policy_version`, `model_id`, `body` (JSON), `state` (`draft` / `published` / `revoked`), `created_at`, `published_at`,
`revoked_at`. Table `delivery_destinations`: `destination_id` (PK), `organization_id`, `channel`, `address_reference`
(never a raw secret), `timezone`, `quiet_hours_from`, `quiet_hours_to`, `severity_floor`, `opt_in_at`, `revoked_at`.
Table `delivery_outbox`: `outbox_id` (PK), `edition_id`, `destination_id`, `dedupe_key` (UNIQUE), `state`
(`pending` / `sent` / `failed` / `expired`), `attempts`, `last_error`, `created_at`, `sent_at`. Delivery audit rows are
written for every terminal state.

### FR-DATA-08 — Tenancy ownership

Every table holding customer-private records gains an `organization_id`: `investigation_cases`, `case_evidence`,
`case_notes`, `media_evidence`, `geographic_evidence`, `investigation_jobs`, `advanced_provider_cache`, `ai_analyses`,
`export_artifacts` (new). Foreign keys and indexes are added for the scoping column.

---

## 5. Workspace and interface requirements

### FR-WS-01 — Mission presets
The system shall provide named task templates — at minimum Cyber Research, Country Watch and Conflict Reporting — each
a workspace row with `kind='template'`. Applying a template replaces the current view state atomically and leaves the
previous workspace recoverable.

### FR-WS-02 — Named workspaces and tabs
A reader shall be able to create, rename, duplicate, delete and select workspaces. Selecting a workspace restores its
layers, country filter, regions, period, time basis, viewport and panel layout. The existing view tabs
(`#analysis-tab`, `#feed-tab`, `#military-tab`, `#sentiment-tab`) shall remain and each shall retain its own filter state
within the active workspace. Deleting a workspace shall not delete evidence, cases or matches that referenced it.

### FR-WS-03 — Versioned preference persistence
Reader preferences shall be persisted server-side under `reader_preferences` with a `schema_version`, replacing
tab-only settings for the keys listed in FR-DATA-04. Failed saves shall retain the user's edits and report failure
distinctly from success and from draft.

### FR-WS-04 — Shareable map state
The system shall encode public view state — layers, country filter, regions, period, time basis, category filters and
map camera — into a versioned URL. Opening such a URL in a clean browser shall restore exactly that public state.
The encoding is an **allowlist**: authentication tokens, private queries, case identifiers, notes, saved search terms
and delivery destinations must never appear in the URL. Unknown or future parameter versions shall be refused with a
clear message rather than partially applied.

### FR-WS-05 — Regional presets
Readers shall be able to save named multi-country regions and apply them as a viewport plus country set. Regions shall
be selectable independently of the existing single `#country` filter, and applying a region shall be visible in the
active filter state.

### FR-WS-06 — Layer explanations
Each layer control shall expose, without leaving the page, the layer's location basis, units, expected update
frequency, known coverage limits and license classification. The same content shall be available as text for
assistive technology. This requirement extends the existing layer explanation behaviour to every layer surfaced by
WM-P4 and WM-P6.

### FR-WS-07 — Existing controls preserved
Current behaviour for UTC period selection, unknown-location handling, separate time bases, dark/light theme, fullscreen,
MapLibre clustering and layer topic search shall not regress. `UX-19` and `UX-20` in the plan are `Keep`.

---

## 6. Personal state, change tracking and watches

### FR-PR-01 — Separation of feed enablement from collection
A reader's preference to hide or show a feed shall affect only that reader's view. It shall not stop collection, change
`connector_status`, or alter another reader's view. Administrator collection enablement remains a separate control.

### FR-CV-01 — Change tracking
The system shall identify a new revision of a retained record and surface it once as changed. Repeated collection runs,
page refreshes or worker restarts shall not produce duplicate changed items. Revision identity shall be the existing
content-hash convention used by `webpage_snapshots`/`source_changes`, extended to `external_records`.

### FR-CV-02 — Review cursor and unread state
Each reader shall have a per-feed and per-watch last-reviewed cursor, advanced only by explicit reader action. The UI
shall show unread and recently-changed counts, and a "zero matches" state shall be visually distinct from a
collection-failure state.

### FR-WT-01 — Watches
A reader shall be able to create a watch over any combination of countries, entities, keywords, sources and categories,
with an optional minimum severity. Watches are persisted, enabled or disabled independently, and survive restarts.

### FR-WT-02 — Match explanation
Every match shall record **why** it matched, naming the clause or clauses responsible. Match records shall retain the
matched revision so a later edit to the source record does not silently change the historical match.

### FR-WT-03 — Rule preview
Before a threshold rule or watch is enabled, the system shall evaluate it against retained evidence and show the
matching records and the zero-match case, so the reviewer can see the false-positive load before committing to
scheduled delivery.

### FR-WT-04 — Bounded evaluation
Watch evaluation shall run as a persisted job with a lease, reusing the existing `investigation_jobs` and
`job_locks` machinery. Evaluation shall be bounded by a configurable record window and shall terminate on worker
restart without duplicating matches.

---

## 7. Country dossier and export

### FR-DS-01 — Consolidated country dossier
The system shall present, for a selected country, the existing country context, activity, threats, infrastructure
observations and citations in one view. Every factual block shall link to retained evidence carrying source time,
location basis and missing/stale indicators. The dossier shall reuse existing endpoints and storage; it shall not
introduce a second evidence model.

### FR-DS-02 — No relabelled risk
Country scores, activity indices and sentiment summaries shall retain their existing names and stated methods. Reporting
volume shall not be presented as validated geopolitical risk, and a composite score shall not be formed by merging
constructs that upstream documents define as different.

### FR-EX-01 — Scoped dashboard export
A reader shall be able to export the current dashboard view as CSV scoped to the active workspace's filters and time
basis, and as a printable evidence brief. Exports shall state the filters, time basis and generation time used.

### FR-EX-02 — Private content exclusion
Export and share flows shall present a preview of what will be shared. Restricted content and private notes shall be
excluded unless explicitly permitted, and existing case JSON/Markdown export shall be preserved unchanged.

### FR-EX-03 — Public share of an edition
An edition may be published to a public read-only view only through an explicit publish action, with a matching revoke
action. Drafts are private by default. Customer destinations and private evidence shall never appear in a public share
link.

---

## 8. Briefings and delivery

### FR-BR-01 — Editorial selection
Edition composition shall deduplicate by source family and shall distinguish commentary, updates and durable events.
Two reports from the same source family do not count as corroboration. The editorial policy version used shall be
recorded on the edition.

### FR-BR-02 — Explicit evidence window
An edition shall be composed over a declared window (`window_from`, `window_to`) and a declared source set. The
window, sources, model identifier and policy version shall be retrievable with the edition.

### FR-BR-03 — Grounding
Generated text shall follow the existing citation-ID checks in `backend/ai_output.py` and the labelled-draft pattern.
Ungrounded claims shall be labelled or removed. AI failure shall degrade the edition rather than silently shortening it
without a note.

### FR-DL-01 — One channel first
Exactly one outbound channel shall be implemented initially, selected by pilot users, with explicit per-recipient
opt-in and a working unsubscribe path.

### FR-DL-02 — Scheduling and quiet hours
Scheduled editions shall be timezone-aware and shall respect per-destination quiet hours and severity floors. A
preview mode shall show what would be sent and when, without sending.

### FR-DL-03 — Delivery integrity
Delivery shall use an outbox with a unique deduplication key, bounded retries, expiry, and an audit record for every
terminal state. Restarting the worker around a scheduled run shall not produce a duplicate send. Source-health actions
and on-screen reporting signals are not substitutes for a notification service.

---

## 9. Identity, tenancy and developer access

### FR-ID-01 — Individual identities
Customer access shall use individual identities and sessions rather than a shared administrator token. Existing
protected routes shall keep working under an explicit migration path.

### FR-ID-02 — Organization scoping
All private queries shall be scoped by `organization_id` per FR-DATA-08. A second organization shall not be able to
enumerate another organization's cases, evidence files, jobs, exports, caches or delivery destinations, including
through search results and direct identifier access.

### FR-ID-03 — Account lifecycle
Account deletion shall be an explicit, documented policy covering cases, evidence, media, editions and delivery
destinations. Existing soft-deleted cases are not an erasure mechanism and shall not be described as one.

### FR-ID-04 — Quotas
Per-customer quotas shall be enforced atomically alongside existing global safeguards, and current usage shall be
visible to the customer.

### FR-ID-05 — Credentials
Developer credentials shall be named, expiring, revocable and scoped. Secrets shall be encrypted at rest and never
returned by any endpoint.

### FR-AP-01 — Documented developer contract
`/api` and `/api/v1` shall have an explicit supported surface with published limits. Documented behaviour shall match
deployed behaviour; undocumented endpoints shall not be advertised.

### FR-AP-02 — Read-only agent access
MCP and agent-discovery surfaces shall begin read-only (search, report detail, country summary, indicator evidence) and
shall publish accurate capabilities, limits and provenance. They shall not mutate evidence.

### FR-AP-03 — Embeds
Embeddable surfaces shall expose public-safe data only, with origin controls, attribution requirements and revocable
keys.

---

## 10. Domain feed and map layer admission

### FR-DM-01 — Admission gate
No additional data source shall be enabled without: a `source_permissions` row (FR-DATA-01), a connector status entry,
an explanation string meeting FR-WS-06, and a defined unknown/missing state. The existence of a writable adapter is not
a reason to enable a feed.

### FR-DM-02 — Required per-feed disclosure
Every admitted feed shall display, in its own surface: measurement basis, source and observation time, retrieval time,
geographic precision, units, coverage limits and last successful collection.

### FR-DM-03 — Interpretation limits
The following must not be inferred by the system and must not be presented as findings:

| Observation | Must not be presented as |
| ----------- | ---------------------- |
| Thermal anomaly | Explosion or strike |
| Radiation variation | Nuclear release |
| Disease news item | Confirmed case total |
| AIS transmission gap | Sanctions evasion |
| Protocol share | Internet outage |
| Report volume surge | Validated geopolitical risk |
| Scenario impact score | Currency loss or forecast |
| Predicted satellite footprint | Collection tasking |

### FR-DM-04 — Reference data before live data
Static, versioned reference layers (ports, chokepoints, cables, pipelines, storage, facilities) shall ship before any
licensed live aggregate, and reference routes shall be distinguished from routes observed for a specific vessel.

### FR-DM-05 — Uncertainty retention
Where a feed supplies an uncertainty or confidence value, it shall be retained and displayed. Where a feed does not,
the absence shall be shown rather than defaulted to a confident value.

### FR-DM-06 — Country-aggregate measurements
Where a provider reports an observation at country granularity, the product shall place the marker at the same
country reference point used everywhere else and shall label the precision as regional. It shall not imply a located
incident, and shall not identify an affected network, operator or site.

Where the provider supplies a score, the surface shall state that the score is in the provider's own units and shall
compare magnitudes only within a single response from a single datasource. Marker sizing may encode rank within that
response; it shall not present a raw cross-datasource score as comparable.

The surface shall carry the aggregation method, the underlying datasource, both the measurement window and the event
window, the retrieval time and the provider's original record link. A value the provider did not supply — an
uncertainty in particular — shall be shown as absent rather than defaulted.

A country that cannot be placed shall be reported as unplaced and counted. It shall not be snapped to a neighbour or
dropped silently. An empty response shall not be presented as an absence of disruption.

### FR-LY-08 — Layers outside the record query
A layer whose records come from a source other than the dashboard's own category query shall be excluded from that
query, and enabling it shall issue no request for the dashboard's event, timeline, sentiment or relation feeds.
Enabling such a layer shall change only what the map draws.

Where such a layer requires a credential the reader may not hold, the control shall state that plainly. Absent
credential, refused credential, empty result and request failure shall each be a distinct, visible state; none of
them shall render as an empty map.

### FR-LY-09 — Reference and evidence layers answer hover
Every map layer that draws point features — reference geometry and evidence-API observations alike — shall answer
`mousemove` with a summary card built from the product's established hover structure, so that a reader is not left
working out what an unexplained dot is. The card shall name the feature, state what kind of thing it is before any
claim about the place, carry the provenance fields required by FR-WS-06 and FR-DM-06, and offer a link to the
upstream terms.

A card shall never present a published coordinate or a country aggregate as an observation of activity. Computed
layers with no point features shall be given no card rather than an empty one.

Point features shall remain reachable pointer targets at every zoom level. A layer whose markers are only a few
pixels across at world view does not meet this requirement, and marker size shall grow as the map closes in.

Within a 248-pixel layer panel, a reference layer's controls — registry badge and sourcing control — shall stay on
the same line as the layer name and shall not wrap, overflow the panel, or float detached from the label they
belong to. The layer name shall have room to read rather than being truncated to fit a badge.

### FR-LY-10 — Share-alike attribution
Where a reference layer derives from a source carrying share-alike obligations, the product shall carry that source's
required attribution on the layer's explanation panel, on every feature's hover card, and in a licence record
alongside the data.

The recorded licence text shall state the obligation in plain terms and identify it as applying to redistributed
derived datasets. Accepting such a licence is a product decision recorded by the owner, not a technical default, and
shall be revisited before any commercial offering.

The upstream response shall be identified by hash alongside the exact query used, so a rebuilt registry can be
shown to derive from the same bytes.

### FR-LY-11 — Facility-level registries
A reference layer shall list facilities, not the components of a facility. Where an upstream tag enumerates
individual units, generators or reactors, those shall not be presented as separate facilities, because doing so would
show one site as several unrelated locations.

Co-mapped duplicates of a single facility — the same site mapped as both a node and an area — shall be collapsed.

### FR-LY-12 — Distinct pictograms
Each reference layer shall carry its own pictogram, used identically in the layer panel, the map key and on the map
itself, so that the legend and the map cannot disagree about what a mark is.

Where a layer contains meaningfully different subtypes — a military registry mixing naval and air facilities, for
example — the pictogram shall vary by the subtype the registry records, selected from the feature's own data rather
than from a filter the reader has to remember to set.

Below the zoom at which pictograms are legible, reference points shall render as plain dots. A registry of several
thousand features shall not be drawn as several thousand overlapping pictograms.

Reference geometry shall never displace, hide or crowd recorded evidence. Pictograms shall not participate in symbol
placement, and their pointer target shall remain reachable at every zoom level.

### FR-LY-01 — Reference layer class
The system shall distinguish two classes of map layer and shall not conflate them.

| Class | Derivation | Lifecycle | Evidence contract |
| ----- | ---------- | --------- | ----------------- |
| **Event layer** | A collected, georeferenced record | Decays with its feed; refreshed per collection interval | Per-record provenance, observation time, location precision |
| **Reference layer** | Versioned static asset geometry | Changes only when the asset registry is revised | Registry version, publisher, licence classification, retrieval date |

A reference layer shall be stored as versioned geometry with a stated registry version, publisher, licence
classification and retrieval date. It shall not be presented as an observation, an attribution or a live position, and
its locations shall not appear in event counts, activity measures or anomaly statistics.

Baseline: all 23 existing map sources in this product are event layers. Reference layers do not yet exist.

### FR-LY-02 — Reference data provenance
Each reference layer shall satisfy the existing `geographic_evidence` contract — `precision`, `basis`, `source_url`,
`retrieved_at`, `license_classification` — and shall carry a registry version. A reference layer whose registry
version is unknown shall not render as current.

### FR-LY-03 — Terminator overlay
The system shall provide an optional solar-terminator overlay computed from date and time, with no external data
source. It shall be off by default and shall carry no analytical claim.

### FR-LY-04 — Wiring existing evidence to the map
Where an endpoint already returns evidence that the map does not display, the system shall either wire it to a layer or
record why it is not displayed. The internet-disruption evidence surface is the first case: it already carries
`measurement_from`, `measurement_until`, `method`, `datasource`, `score` and `uncertainty`, and is not currently a
map source.

### FR-LY-05 — Layer admission
A new map layer shall not ship unless it satisfies FR-DM-01 through FR-DM-05 and declares which class it belongs to.
Adding a layer because an adapter can be written is not a reason.

### FR-LY-06 — Declined layers
The following shall not be added as map layers absent a validated method meeting §11.6: country instability scores,
country resilience scores, and any composite that presents reporting volume as validated geopolitical risk. Their
absence from the product is a recorded decision, not a gap.

### FR-LY-07 — No approximated reference geometry
A reference layer shall not ship unless its geometry can be traced to a named upstream source whose terms permit
redistribution, with the retrieved bytes identified by hash. Where no such source exists, the layer shall be left
unimplemented and recorded as blocked. Hand-entered coordinates, recalled place lists and inferred positions shall
never be presented as a published registry, regardless of how plausible they appear.

Where upstream data is derived, the extraction shall be checked in as a reproducible script and the resulting file
shall record the upstream hash alongside the publisher, licence and retrieval date. Where a coordinate cannot be
resolved — for example a coastal point that a boundary test does not cover — the field shall be left empty rather
than guessed.

---

## 11. Non-functional requirements

### 11.1 Resource discipline
The 8 GB target and existing bounded-collection, feed-text and worker-lease behaviour shall hold. Watch evaluation,
briefing composition and delivery shall be bounded jobs, not request-path work. New tables shall be indexed on their
scoping and lookup columns.

### 11.2 Performance
Workspace load, preference load and watch evaluation shall not block the dashboard's first render. Persistence calls
shall be debounced where they follow rapid user input, and shall never delay map interaction.

### 11.3 Security
Credentials are never placed in URLs, exports or logs. Share and export paths are allowlist-based. Private records are
organization-scoped. Existing security requirements in OSINT-SRS-001 remain in force.

### 11.4 Accessibility
New controls shall be operable by keyboard without drag gestures, shall have accessible names, visible focus, and
correct focus handling on dialog open, close and failure. Text-size preferences shall be tested against the dense
evidence tables the dossier introduces.

### 11.5 Auditability
Workspace, preference, watch, edition and delivery mutations shall be recorded in the existing `audit_log` with actor,
resource and timestamp. Delivery shall additionally write terminal-state audit rows.

### 11.6 Methodological integrity
Any score, composite or index introduced under WM-P7 shall declare its purpose, version its inputs, define
missing-data behaviour, be evaluated against historical outcomes, and expose an explanation a user can inspect.
Absence of that work is a reason not to ship the number.

### 11.7 Honest reporting
Documentation and status files shall distinguish `Existing`, `Partial` and `New` accurately, and shall not claim a
capability was exercised when it was only read in source or documentation.

---

## 12. Acceptance conditions

The first release is accepted when all of the following hold. These mirror plan §H and are the exit criteria for WM-P2
and WM-P3.

| # | Deliverable | Observable completion condition |
| - | ----------- | ------------------------------- |
| AC-01 | Saved workspace | A named country/topic/provider/time-basis/layer selection saves, reloads and is recovered. Invalid old preferences migrate or reset safely. |
| AC-02 | Shareable map | A shared URL opened in a clean browser recovers only public view state. Credentials, private queries and case identifiers are excluded. |
| AC-03 | Personal source filters | One reader's preference changes their feed without disabling collection for everyone. |
| AC-04 | Change tracking | A new source revision appears once as changed; refresh alone does not create a new unread item. |
| AC-05 | Watchlist | Each record explains why it matched, retains the relevant revision, and shows zero matches distinctly from collection failure. |
| AC-06 | Country dossier | Every factual block links to retained evidence with source time, location basis and missing/stale indicators. |
| AC-07 | Brief edition | The selected window, sources and model/policy metadata are preserved. Source-family duplicates do not count as corroboration. |
| AC-08 | Private/public export | What will be shared is previewed; restricted content and private notes stay out unless explicitly permitted. |
| AC-09 | Scheduled delivery | Restarting the worker around a scheduled run sends nothing twice; quiet hours and unsubscribe still apply. |
| AC-10 | Customer isolation | A second account cannot enumerate another account's cases, evidence files, jobs, exports, caches or delivery destinations. |
| AC-11 | Feed admission | Every enabled feed has a permission row, an explanation surface and a visible unknown state. |
| AC-12 | Reference layer integrity | Every reference layer states its registry version, publisher and licence; its geometry is excluded from event counts and activity measures. |
| AC-13 | Declined layers | No country instability or resilience score is rendered as a map layer or an official rating. |
| AC-14 | Backlog hygiene | `docs/TODO.md` reflects the delivered state after every phase, including anything deliberately left open. |

---

## 13. Traceability

Plan section → requirement → phase.

| Plan group | Requirements | Phase |
| ----------- | ------------ | ----- |
| A — map, interface, workspaces | FR-WS-06 | WM-P1 (every new layer carries its explanation surface) |
| A — workspaces, export, interface depth | FR-WS-01…05, 07, FR-EX-01, FR-EX-02 | WM-P4, WM-P7 |
| B — briefings, AI, research output | FR-BR-01…03, FR-AP-02 | WM-P5, WM-P7 |
| C — watchlists, notifications, integrations | FR-WT-01…04, FR-DL-01…03 | WM-P4, WM-P5 |
| D — developer access, packaging, commercial | FR-ID-01…05, FR-AP-01…03 | WM-P6 (pre-sale), WM-P7 |
| E — domain additions | FR-DM-01…05 | WM-P2, WM-P3 |
| Catalog map-layer registry (`MAP-01…58`) | FR-LY-01…06 | WM-P1, WM-P2, WM-P3 |
| F — preserve existing | FR-WS-07 | all |
| G — build sequence | §12 acceptance conditions | WM-P0…WM-P5 |
| I — licensing and method | FR-DATA-01, FR-LY-06, §11.6 | WM-P0, WM-P7 |

Catalog rows are itemised in [`docs/TODO.md`](docs/TODO.md), including the full 58-row layer inventory with Signal
Atlas anchors.

**Build order.** Layers are Phase 1. Owner priorities recorded 2026-10-16: all three monitoring domains (cyber,
country research, disruption) are in scope, no sales in the near term, and map layer implementations rank ahead of
workspaces, briefings and platform work. Identity and tenancy (WM-P6) is therefore a gate that must be cleared before
the first paid customer rather than a prerequisite for feature development.

### Layer coverage baseline

Measured 2026-10-16 against the running application and against `src/map.js` (`addSource` lines 936–1629),
`src/main.js` (toggle categories, line 72) and `backend/connectors/registry.py`. The live layer panel exposes exactly
10 toggles, all record-derived, with 147/186 sources current and no console errors.

| Class | Registry layers | State |
| ----- | --------------- | ----- |
| Event layers present | Orbital Surveillance, Military Activity, Aviation, Cyber Threats, Fires, Internet Disruptions | 6 |
| Event layers partial | Intel Hotspots, Conflict Zones, Ship Traffic, Protests, Armed Conflict Events, Natural Events, Sanctions | 7 |
| **Reference layers present** | Day/Night terminator (computed), Ports (Natural Earth), Military Bases, Nuclear Plants, Spaceports (OpenStreetMap) | **5** |
| Reference layers blocked | Gamma Irradiators (not in OSM), Chokepoints (no canonical dataset) — **not** approximated | 2 |
| Absent and declined | Country Instability, Resilience | 2 |
| Absent, building next (WM-P2) | 17 | — |
| Absent, licensed and gated (WM-P3) | 9 | — |
| Absent, skipped or deferred (WM-P7) | 10 | — |

---

## 14. Open decisions

Carried from plan §J. Each selects scope; none blocks specification.

1. Which customer task is the first paid pilot? **Answered 2026-10-16: all three — cyber monitoring, country research,
   operational disruption monitoring.**
2. Which sources permit commercial display, storage, exports and alerts for those tasks? Open; blocks WM-P3.
3. Does the first release serve isolated installations or a shared SaaS? Open, but not urgent — deferred to WM-P6.
4. Which single delivery channel and digest cadence do pilot users actually need?
5. What false-positive rate and review burden are acceptable for each alert or score?

Licensed-feed availability, commercial licence terms, Enterprise contracts and any predictive performance remain
unverified. Re-check provider terms and official documentation before enabling any source or buying access.
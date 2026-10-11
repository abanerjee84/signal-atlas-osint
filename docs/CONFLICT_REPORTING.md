# Conflict reporting and map signals

Collection uses ordinary public HTML and publisher-offered feeds without new keys or paid APIs. Sources supply partial reporting, not a complete or independently verified picture of conflict. The [source audit](CONFLICT_SOURCE_AUDIT.md) records tested links, upstream citations, failed candidates and background datasets.

## Connected sources

- **Liveuamap:** Ukraine, Israel–Palestine, Sudan, Myanmar, Sahel, Yemen, Iran, Asia and Latin America. Two layer selectors share one HTML response per region; they are not independent sources.
- **Military publishers:** Long War Journal, Defense News, Naval News, The War Zone and DefenceWeb.
- **Regional/investigative feeds:** Irrawaddy, Times of Israel, Anadolu, Ukrinform, Kyiv Independent, Bellingcat, Sudans Post, Khaama Press, Dawn, Premium Times, Agência Brasil, Taipei Times and Middle East Eye. Explicit military wording routes individual records to Military OSINT; diplomacy, governance, protests and ordinary security reporting go to Geopolitics.
- **ISW:** actual public research articles discovered from its homepage, with original publication metadata and short source summaries. Assessment tags distinguish analysis from incident reporting. Existing Crisis Group RSS adds further assessments.
- **Existing official sources:** NATO, UK Ministry of Defence and DVIDS participate in the public collection lane.

The new additions represent **28 public source endpoints** and **37 connector selectors**: nine regional maps, 18 feeds and ISW. Copies and upstream social accounts do not become independent corroboration when several collectors encounter them. Aircraft telemetry is never used to infer military activity.

Liveuamap currently serializes editorial events in a base64 JSON initializer. The bounded parser locates payloads structurally without evaluating scripts and reads only `venues`. Static landmarks and natural disasters are excluded. Invalid coordinates, missing dates, dates more than an hour ahead and records outside the 180-day retention window are rejected. Original publication time is preserved; occurrence time remains unknown unless supplied.

The Liveuamap permalink and linked original sources are retained together. Its coordinates are **approximate**, not precise unit positions. Publisher base countries never replace event coordinates. Feed country mentions supply **regional context** only when one country is unambiguously named; other items remain unlocated. Attacking countries, casualties and severity are not invented from icons or keywords. [Liveuamap reuse terms](https://liveuamap.com/about#terms) require attribution, and upstream resources retain their own terms.

RSS, Atom and RDF publication dates use the existing bounded parser. HTTP decompression handles gzip. Irrawaddy appends analytics after its complete RSS document; its connector discards that trailer and retains strict entity-safe XML parsing. Scripts and media are never executed or fetched. Only headlines and short excerpts are stored.

## Symbols and hover summaries

Fourteen pictograms identify sirens/evacuations, drones, airstrikes, missiles/rockets, artillery, bombs/explosions, fighting, naval activity, deployments/exercises, weapons, diplomacy/ceasefires, protests, security/violence and other conflict reporting. The expandable **Conflict symbols** key explains them. They describe reporting topics, not confirmed actions.

Solid rims indicate approximate reported locations; dashed rims indicate country context. Colours identify layers rather than severity or truth. Homogeneous clusters use the topic symbol and count; mixed clusters remain bundles and expand on selection. Country-level military markers represent briefing context, not troop positions.

Hover previews use stored source wording or an existing source-grounded summary. Individual markers show topic, summary, location basis, publication time, confidence and source domain. Cluster previews include up to three source summaries. Military country markers include up to two relevant headlines. Clicking opens evidence and available original-source links. No LLM is needed for hover summaries.

## Reporting signals & alerts

This derived layer replaces **Analysis and anomaly alerts**. Its sidebar switch and map-menu **Reporting overlays** switch now control one persisted state. Enabling it opens report evidence rather than the AI form. Signal text survives refresh, and its badge counts derived signals rather than attacks or stored analysis events.

- **Amber regional rings:** a 10-degree cell has at least 20 records across 72 hours, at least five in the final six hours, at least two in the preceding six hours, and at least three times the preceding count. The selected end/time basis anchors comparisons; the selected start does not truncate baseline history. Rings mark coarse reporting areas, not incidents.
- **Teal country rings:** at least two enabled categories each have three or more records associated with a country in the past 24 hours. This is reporting overlap, not a causal or coordinated link. Country totals follow category, country, search and period filters; viewport clipping does not truncate these totals. Historical windows outside the current 24 hours do not provide this live overlap signal.
- **Inspection:** country actions apply a country filter; area actions focus the map and enable its viewport filter. Conflict/geopolitical reporting supplies evidence when the derived layer is selected alone.

Provider coverage, editorial focus, deduplication and collection timing can create reporting surges. These signals do not establish escalation. Optional cited AI analysis remains a separate tab.

Adjacent filter changes share one request batch; the automatic refresh waits for any current refresh to finish. This avoids repeating expensive reporting queries while leaving the existing servers running.

## Collection and verification

Regional HTML is checked every 15 minutes; publisher feeds and ISW every 30 minutes. The approved gatherer checks due batches independently of its ten-second cyber lane, including existing regional/official feeds. Database leases prevent overlap with the normal worker. Failures retain last-good data and respect backoff. The gatherer opens no listening socket.

A public aggregate health bridge exposes new sources to an API process already running. The frontend includes their health and mixed-feed military coverage without starting, stopping or restarting either server.

`scripts/check_conflict_workspace.py` verifies real hover summaries, citations, symbols, unified switches, persistent alerts, military briefs and narrow layouts against the running dashboard. Synthetic fixtures remain in temporary test databases. `scripts/reclassify_conflict_reports.py` repairs these collectors' labels from stored public evidence while preserving original dates and raw records.

See [UI checks](conflict-ui-verification.json) and [collection checks](conflict-ingestion-verification.json). CFR and UCDP were investigated as background/history references and are not displayed as a fabricated live incident stream. ACLED's existing authorized connector remains separate because its site terms prohibit HTML scraping.

All 37 selectors have completed a successful collection at least once. Subsequent checks can fail: Premium Times later served a JavaScript access challenge, and one Myanmar politics snapshot contained no valid records within retention. Those failures remain visible in source health; previous evidence is retained. The verification file records current states separately from past successful collections.

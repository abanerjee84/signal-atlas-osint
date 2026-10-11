# Dashboard performance

The October 11, 2026 optimization preserves the reporting samples, country matching rules, source cadence, historical filters and evidence links.

## Measured improvements

Measurements used the existing local API and Vite dashboard, a 1600×1000 Chromium window, and the retained live database. No measurement starts or stops a server. These are observations on this machine, not guaranteed latency targets for other devices.

| Measurement | Before | After |
| --- | ---: | ---: |
| Dashboard initially ready | 6.43 s | 3.31 s |
| Dashboard refresh ready | 8.11 s | 1.90 s |
| Extract countries from 1,000 stored reports | 1.85 s | 0.10 s |

The country benchmark runs the original country matcher alongside the optimized implementation on the same 1,000 stored report titles and excerpts. Every country result matches. A second comparison measured an 18.4× improvement. A repeat dashboard check, while another browser check ran, opened in 4.29 s and refreshed in 2.01 s, retained card focus and passed a 5-second refresh budget. Dataset changes, database cache state, browser rendering and concurrent collection affect dashboard timings.

## Changes

- Country extraction selects candidate countries from complete words before applying the original country/alias expressions. It preserves overlapping place names, word boundaries, Unicode case matching, abbreviation handling and the existing exclusions for Indian Ocean and British Columbia. It does not cache reporting or infer new locations.
- Unchanged event cards keep their existing DOM nodes, icons, keyboard focus and measured heights. Removed cards leave the bounded cache; changed evidence still updates. Offscreen cards use browser rendering containment while remaining available for scrolling and keyboard navigation.
- A dashboard refresh renders its event feed once after panel state is ready. Live aircraft updates no longer force unchanged report geometry back through the map worker. Conflict classification is computed once per feature, and repeated network assignments are skipped.
- Map diagnostics inspect all relevant layers in one traversal instead of repeatedly scanning rendered features. Interactive hover hit tests stay separate. Arrow animation, reduced motion behavior and the collection pace are retained.
- Cyber report and provider sample queries explicitly select the threat category before applying their existing text filters, avoiding unrelated categories in the main row selection. The per-provider sample limits and geographic balancing remain intact.

## Verification

`scripts/benchmark_dashboard.py` records readiness, individual request durations, long browser tasks and unchanged-card/focus retention. Pass `--require-card-reuse` and an environment-appropriate `--max-refresh-seconds` to turn it into a performance regression check. It requires an existing dashboard and `--chromium` pointing to an installed browser.

Run `scripts/benchmark_country_matching.py` with the repository on `PYTHONPATH`; `--require-speedup` verifies identical extraction and at least a 3× speedup over the original matcher. It reads retained reporting without displaying or exporting report text. Backend regression tests also compare all country names/aliases, overlapping country names and Unicode cases against the original rules.

Browser checks cover cyber evidence, moving arrows, reduced motion, social sentiment, military links, filters, reporting signals and progress behavior. Routine refresh remains quiet; progress is reserved for user-triggered computation.

Normal deployment must load updated backend code to receive the country-matching improvement. The existing server processes were left under the user's control throughout this work.

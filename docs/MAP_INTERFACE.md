# Map symbols and country comparison

Each layer uses the same shape and monogram in the map, switches and event list:
GP hexagon (geopolitical), MI shield (military), MT hull (maritime), S speech bubble
(sentiment), CY chip (cyber), EC diamond (economic), EN leaf (environment), and
ST satellite. Aircraft retain the yellow plane, restricted to ADS-B
classes 4 and 5 with an actual reported track. P identifies a publisher base.

Geopolitical and military reports additionally use fourteen topic pictograms,
including bombs, drones, rockets, artillery and sirens. The **Conflict symbols**
key explains them; hover previews summarize stored evidence, with location,
UTC publication time and source. Homogeneous topic clusters retain that
pictogram. See [conflict reporting and reporting signals](CONFLICT_REPORTING.md).
The former analysis overlay is now **Reporting signals & alerts**, with one
top **Signals** button, separate from Intelligence layers; optional AI remains separate.

Solid symbols mark reported locations; hollow dashed symbols mark regional
context. Cluster badges show loaded observation counts, with 99+ for larger
clusters. A cluster containing one category keeps that category's shape; + marks
mixed categories. All-regional clusters remain hollow. Selecting a cluster
expands it, and its hover preview shows two short source summaries.
The Key control explains these conventions. Unlocated records remain in the feed.

The collapsible Countries ribbon sits at the map's left edge. It shows the top
12 countries and retains a selected country when that country ranks lower.
Keyboard or pointer selection focuses and filters the map. Clearing selection
returns to the worldwide comparison. Mobile initially collapses the ribbon;
collapse state and ranking mode are remembered for the browser session.

- Mentions: distinct original reporting/discussion URLs naming each country,
  including explicit thread-country context, plus source count. Aviation
  telemetry and unscored environmental detections are excluded. Mentions use
  the active event filters, with a disclosed limit of 5,000 latest report URLs.
  A URL naming several countries counts once for each country.
- Sentiment: the selected sentiment panel dataset, platform and geography,
  independently of physical overlay switches. Uses publication dates. Order can
  be most negative or most positive. Samples of at least five texts rank before
  smaller samples; the latter are labeled thin. Missing scores are omitted.
  The panel's existing 2,000/5,000-text bounds and retention rules apply.
- Intel: active intelligence-layer breadth, followed by verified/corroborated
  records, then record count. Each row shows layer symbols and complete matching
  event totals, including events beyond the loaded map sample. Aviation,
  sentiment and generated analysis are excluded from this ranking.

The comparison ignores country selection so it remains useful when moving
between countries. Period, search, time basis, active categories and requested
viewport still affect intelligence totals and mentions; sentiment follows its
own documented dataset filters. Country references and regional assignments do
not locate an incident. Intelligence breadth is coverage, not a threat score.
Wording scores are not national opinion or sentiment toward a country.

`GET /api/country-activity` returns the comparison using the normal dashboard
filters plus `kind`, `platform` and `geography`. The ribbon refreshes independently
of the main map and shows an unavailable state on failure. No new provider keys,
authentication changes or schema migration are required.

Verification: 152 backend tests, four geometry/aircraft tests, nine browser tests
including the production bundle under deployment CSP, production build, Python
lint and frontend formatting passed. Browser coverage includes marker categories,
homogeneous/mixed clusters, retained aircraft, sample-aware ranking, keyboard
country selection, persistent collapse and mobile fit.

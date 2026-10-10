# Aircraft, economic coverage and AI output update

## Current aircraft and card details

OpenSky now has a dedicated collection lane, normally every 120 seconds. Other
feed jobs no longer delay it behind a whole collection cycle. OAuth tokens are
reused until expiry; quota backoff is respected. The global two-minute schedule
uses about 2,880 state-request credits per day before failures or other clients;
the [OpenSky REST documentation](https://openskynetwork.github.io/opensky-api/rest.html)
lists a standard authenticated allowance of 4,000 and a global request cost of four.
The interval can be increased with `OSINT_OPENSKY_POLL_SECONDS` (120–1800).

`/api/aviation/live` reads a bounded, atomically replaced current snapshot instead
of competing with all other layers for the 500-record historical page. Only
declared ADS-B classes 4 and 5 with a reported position and track qualify; the
400-position geographic sample is preserved. The browser checks the local
snapshot every 15 seconds when Aviation is enabled and the tab is visible.
Aircraft counts show current positions in that view. Period, country, search
and viewport filters still apply. Custom dates and history playback use retained
observations. Retained history keeps the previous 30-minute cadence; existing
records are preserved. Migration 006 adds the current snapshot table.

New observations animate for eight seconds from the previous reported position.
Longitude and track follow the shorter direction across the dateline and north.
Old observations, long gaps and implausible jumps snap directly. Animation stops
when the map is offscreen, the tab is hidden or reduced motion is requested. No velocity extrapolation
or invented route is displayed. Positions older than ten minutes are excluded
from the current snapshot response; delayed collection is labelled. A failed
collection keeps the last successful snapshot, while a successful empty result
clears it.

Aircraft feed cards show registration country, barometric altitude in feet and
metres, speed in knots and km/h, track, and observation age. Details also show
ICAO24, geometric altitude, vertical rate and airborne/on-ground status where
available, alongside the original source link. Missing values remain unknown.
Registration country is explicitly distinguished from departure origin;
OpenSky state vectors do not provide departure or destination airports. Clicking
a card zooms to its position so movement is easier to see. Other feed cards now
include a short source excerpt.

## Economic and energy

The old layer had only ECB releases and recent OFAC sanctions guidance. OFAC's
feed contained no recent qualifying items and the newest ECB release was outside
the default 24-hour window. A healthy feed could therefore still produce zero.

Five free publisher feeds now supplement those sources: BBC business, Guardian
business, Guardian energy industry, CNA business, and US EIA Today in Energy.
Feed excerpts retain attribution, publication time and original links. Explicit
country mentions provide regional context; publisher location is not substituted
for event location. Articles without a supported location remain in the feed.
Malformed dates are rejected rather than replaced with today's date.

Live verification found **25 economic records in the last 24 hours, 12 with
supported regional map context**. Two OpenSky snapshots 118 seconds apart shared
151 aircraft; **138 had changed their reported position**. These are observations
from the verification run, not guaranteed future counts. The summary is saved in
[aircraft-economic-verification.json](aircraft-economic-verification.json).

## LLM response handling

Both dashboard analysis and advanced assessments accept provider text without
requiring a schema-capable model. Bounded local parsing recovers valid JSON from
prose wrappers and Markdown fences. Existing schemas and citation membership
checks still apply to structured claims. Unsupported citation IDs are rejected.

Plain text, truncated JSON and schema mismatches are shown as an **unvalidated
AI draft**, with no structured claims or verified citations. Supplied sources
are labelled as context. Drafts are cached and counted against the same request
budget; formatting does not trigger another model request. Text is displayed
as text, never executed as HTML. Empty messages and invalid provider envelopes
remain errors. Cache versions changed so old outputs cannot bypass the new
handling. Citation membership does not independently verify a claim's truth.

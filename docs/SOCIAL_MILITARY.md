# Social discussion, news connections and military evidence

Implemented and checked on 10 October 2026. These collectors use public endpoints and require no social API keys. The private `.env` was not changed for this work.

## Reddit without RSS

A second working route is an explicit capture of visible public posts/comments in the signed-in browser. Ordinary browser access succeeded where Reddit's server JSON listing was blocked. The public thread and two visible comments were captured with their original timestamps, post IDs, authors, permalinks and thread context. Ads, navigation, account details, cookies and private content were excluded.

The dashboard accepts a JSON file or pasted snapshot text under Sentiment → Import captured Reddit posts. Pasting works without enabling the browser extension's local file access. The protected `POST /api/admin/social/reddit-browser` validates original public Reddit references, configured communities, IDs and timezone-qualified publication timestamps before atomically replacing the browser snapshot. It does not fetch Reddit or control the browser. A local access token protects the import; no social API key is involved. Browser collection is an explicit/manual sample, not unattended polling. These records share the 24-hour expiration and backup exclusion rules.

For an assistant-assisted refresh: open a public thread through the supported browser tool, read only its visible post/comment text and DOM-backed ID/date/permalink attributes, then import the bounded capture through the protected endpoint. Do not read account/session state or bypass browser challenges. The capture format is the API's `BrowserCapture` schema. At most 100 records and 64 KB are accepted per request.
The independent [Arctic Shift JSON API](https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md) is integrated as separate post and comment collectors for the configured communities. It requests up to 25 items from the preceding seven days once per hour. It requires no key, login or payment. Collection uses original creation times; archived content is not presented as a live stream. Actual reply and thread identifiers become relationship edges. Deleted/removed wording is excluded.

Live verification returned HTTP 522/523 from Arctic Shift. The dashboard exposes that failure and retries on the normal schedule; it does not invent records or silently label RSS as JSON. Reddit's unauthenticated public JSON listing returned 403. A documented public PullPush archive search returned 429; that service is not connected. No host rotation, cookie extraction or access-control bypass was introduced.

Existing Reddit Atom collectors remain separately visible. One successful r/worldnews post snapshot supplied 25 records; other community/comment feeds returned 429. [Reddit announced RSS retirement on 13 November 2026](https://www.reddit.com/r/modnews/comments/1wubgvt/continuing_our_infrastructure_updates_whats/). Neither this snapshot nor the archive is a guaranteed comprehensive feed.

## Sentiment and relationship evidence

The default Sentiment dataset is public discussion wording. English [VADER](https://github.com/cjhutto/vaderSentiment) compound scores use positive >= 0.05 and negative <= -0.05. Uncertain, short or non-English wording remains visible but is excluded from scoring. A comment's body is scored separately from its thread title. Negation and emphasis are heuristic; sarcasm, stance and sample bias remain limitations.

The map can show countries named in the text or thread context, or explicitly supplied origins. Heatmap intensity reflects bounded sample counts; colour reflects mean wording score. The collected public feeds provide no supported author origins: origin mode correctly has no geographic heatmap. A country mention never becomes an inferred residence. Country co-mentions have supporting report IDs and original links. The discussion graph renders only explicit comment/thread/reply relationships, with unsampled targets marked as outside the sample. Unlinked posts remain in the source list. The graph and post list have bounded samples, disclosed in the response and UI.

Duplicate deliveries are deduplicated by platform and post ID. Public discussions are replaced after each successful source snapshot, expire locally after 24 hours, and are excluded from database backups. Failed refreshes retain the previous snapshot until expiration and visibly show their error.

Three public YouTube channel feeds provide 45 upload titles/descriptions. They are a separate media dataset, not viewer comments. X has no keyless collector connected; it returns a clear empty dataset rather than a fabricated sentiment measure.

## Broader news and the map

BBC world and six regional feeds, Al Jazeera, DW, Guardian and France 24 have been collected successfully. RSS 1.0/RDF, RSS 2.0 and Atom are supported. Only feed excerpts are collected. Original references and publication timestamps remain attached.

Solid gold lines join configured publisher base countries to countries discussed. Dotted lines join countries named together. Clicking a line exposes supporting stories; clicking a publisher marker names its source. Great-circle curves are split at the dateline. A bounded 1.8-second highlight marks newly loaded reports and respects reduced-motion preferences. These lines describe reporting context, not movement or verified influence.

## Military evidence briefing

[DVIDS publishes a public news feed](https://www.dvidshub.net/about/faq); its successful live pass stored 20 reports. UK Ministry of Defence Atom announcements are also connected. NATO's legacy feed remains unavailable, and ACLED data access remains denied. Official reporting is predominantly US/UK and carries institutional bias; the view does not claim complete global military coverage.

The Military tab combines official announcements with media reports that contain explicit defence/conflict wording. Topics cover exercises/readiness, procurement/capability, defence cooperation, conflict reporting, defence policy, other official reporting and historical background. Civilian training wording alone is excluded. Topics can overlap. Historical retrospectives are separated from current reporting.

Each topic provides original dated references, official/media labels, source diversity, country mention counts, unknown-geography counts and publication-volume comparisons between the earlier and later halves of the chosen window. These comparisons describe reporting volume, not operational activity. Sources are not automatically declared independent or corroborated.

“Show on map” selects that topic's pink evidence connections and country context markers. “Inspect evidence on map” opens the stored event and uses supported location context where available. “Prepare cited analysis” selects up to 30 associated events for the existing protected, free-only OpenRouter analysis. Every returned claim must validate against supplied citation IDs; invalid model output is rejected. Source_kind now accompanies the AI evidence packet. No military identity is inferred from civilian aircraft tracking.

## Verification

- 74 backend tests, including discussion scoring, duplicate delivery, language exclusion, snapshot deletion, backup exclusion, archive reply provenance, YouTube separation, country filtering, historical separation and civilian-training exclusion.
- Two geometry tests cover dateline crossing, coincident and antipodal anchors.
- Python lint, formatting checks and production build pass.
- Actual source health and 24-hour counts are recorded in `intelligence-verification.json`. Counts vary with the window and new collection.
- Browser checks cover topic map selection, origin mode, source evidence, YouTube separation, empty X coverage and source-health failures. A free-model defence-cooperation assessment succeeded with validated citations; reuse returned the cached result. An earlier malformed response was rejected. Free AI output is accepted only after schema and citation validation.

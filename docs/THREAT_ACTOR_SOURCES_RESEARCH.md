# Threat actor and cyber source assessment

Reviewed on 11 October 2026 IST. Direct HTTP probes ran on 10 October at 18:49–18:51 UTC. This is a source assessment, not a new collection deployment. No credentials, accounts, subscriptions or dashboard data were changed.

Implementation followed this assessment: see [Threat intelligence integration](THREAT_INTELLIGENCE.md) for deployed collectors, actor/campaign graph placement, actual counts and current limitations. The observations below describe the earlier research pass.

The discovery list was [jivoi/awesome-osint](https://github.com/jivoi/awesome-osint), especially Threat Actor Search, Specialty Search Engines and OSINT RSS Feeds. Its inclusion of a website does not establish permission to scrape that website. MITRE ATT&CK below is an additional first-party recommendation, rather than a claim that it is directly listed in that repository.

## Recommended sources

| Source | Public access checked | What the dashboard can use | Restrictions and priority |
| --- | --- | --- | --- |
| [MISP Galaxy](https://github.com/MISP/misp-galaxy) | HTTP 200; valid [threat-actor JSON](https://raw.githubusercontent.com/MISP/misp-galaxy/main/clusters/threat-actor.json), 1,060 entries, version 352; no authentication | Stable UUIDs, names, aliases, descriptions, references, related objects and available attribution metadata | Best initial actor catalog. JSON is dual licensed with a [CC0 option](https://raw.githubusercontent.com/MISP/misp-galaxy/main/LICENSE.md). Reference knowledge, not a live incident stream. |
| [MITRE ATT&CK](https://attack.mitre.org/resources/attack-data-and-tools/) | Official [collection index](https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/index.json) returned HTTP 200 and three domain collections without authentication | STIX groups, software, campaigns, techniques and documented relationships | Best complementary behavior graph. MITRE documents STIX JSON ingestion. Full domain bundles were not downloaded in this review. [License](https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/LICENSE.txt) allows research, development and commercial use with its copyright notice and license preserved. |
| [Malpedia](https://malpedia.caad.fkie.fraunhofer.de/usage/api) | Actor list and actor metadata endpoints both returned valid JSON, HTTP 200, 1,060 entries; no authentication | Actor aliases and references; public family metadata can provide further malware context | Public actor endpoints are explicitly documented as having no access limitation. [Terms](https://malpedia.caad.fkie.fraunhofer.de/usage/tos) specify CC BY-NC-SA 3.0. Private samples and other restricted content have separate access requirements. Use as enrichment, with source lineage retained. |
| [ETDA / ThaiCERT Threat Group Cards](https://apt.etda.or.th/cgi-bin/listgroups.cgi) | Its officially linked [JSON export](https://apt.etda.or.th/cgi-bin/getcard.cgi?g=all&o=j) returned HTTP 200 and 503 entries without authentication | Actor names, naming vendors, country associations, descriptions, references and card revision dates | Optional historical reference. Export declares CC BY-NC-SA 4.0 and last database change **2025-08-16**. The HTML page says 504 groups; use the actual validated export count and display the stale revision date. |
| [SANS Internet Storm Center](https://isc.sans.edu/xml.html) | Full diary RSS: HTTP 200, 10 items. A bounded top-IP JSON query: HTTP 200, 10 items. No authentication | Dated analyst reports and sensor-derived IP/port summaries | Best initial activity source. [API documentation](https://isc.sans.edu/api/) requires respectful access, describes no current authentication, requests a contact-bearing custom User-Agent, and specifies backing off for five minutes or Retry-After on HTTP 429. It prohibits resale and names CC BY-NC-SA 4.0. |
| [Citizen Lab](https://citizenlab.ca/) | [RSS](https://citizenlab.ca/feed/) returned HTTP 200, valid RSS and 10 items without authentication | Spyware investigations, surveillance infrastructure, influence operations, affected organizations and countries | High priority for investigative reporting. The feed includes media mentions and events as well as original research; preserve that distinction. Public feed access does not establish a blanket full-text redistribution license. Start with linked metadata and permitted excerpts; inspect report-specific terms before archiving reports. |
| [Krebs on Security](https://krebsonsecurity.com/about/) | [RSS](https://krebsonsecurity.com/feed/) returned HTTP 200, valid RSS and 10 items without authentication | Cybercrime investigations, incident reporting, named groups and affected organizations | Useful reporting source. Keep publisher attribution and original links. No blanket republication license was established. The response had a text/html content type but parsed as RSS, so validate the body rather than trusting the header alone. |
| [defend.network](https://defend.network/about.html) | [RSS](https://defend.network/feed.xml) returned HTTP 200, valid RSS and 25 items without authentication | Discovery of relevant public briefings and their cited original reports | Lower priority: the provider states briefings are generated automatically without manual editorial review. Label these as automated secondary analysis. Follow cited original sources before adding high-confidence attribution or counting corroboration. No blanket republication license was established. |

Exact statuses, counts, response formats and tested URLs are saved in [osint-candidate-feed-verification.json](osint-candidate-feed-verification.json). Availability at one check is not an uptime guarantee or proof that every claim in a dataset is correct.

## Duplicates and evidence quality

The MISP and Malpedia actor responses shared **all 1,060 actor UUIDs** in this check. They must not count as 2,120 distinct actors or two independent confirmations. Keep both source records when useful, resolve shared identifiers, and follow the cited underlying reports. Matching UUIDs establishes catalog overlap; it does not establish that all fields are identical.

Similarly, an automated briefing that quotes an advisory and the advisory itself describe one evidence lineage. Count independent investigations separately from syndicated or summarized reporting.

SANS warns that its top-source-IP data contains false positives and is [unsuitable as a blocklist](https://isc.sans.edu/xml.html). IP observations describe network activity. They do not identify the responsible human, group, sponsor or physical attack origin.

## Sources to hold back

| Candidate | Finding | Decision |
| --- | --- | --- |
| Shadowserver public dashboard | Its [statistics terms](https://www.shadowserver.org/statistics/) permit attributed research use but explicitly prohibit scraping and resale. Its [report API](https://www.shadowserver.org/faq/how-are-reports-delivered/) requires arranged access. | Keep an analyst reference link. Do not scrape the dashboard or its internal requests. |
| URLhaus | Current [community API documentation](https://urlhaus.abuse.ch/api/) requires an Auth-Key, including dataset downloads. Community use is free subject to fair-use principles; commercial use can require a subscription. | Hold outside the no-new-key shortlist. |
| MalwareBazaar | Current [API documentation](https://bazaar.abuse.ch/api/) requires an Auth-Key. | Hold outside the no-new-key shortlist. This review did not download malware samples. |
| FortiGuard, BI.ZONE, BreachHQ, OpenHunting | Actor pages are discoverable through the directory. A documented no-key bulk export and applicable automated-use permission were not established in this review. | Useful manual references; do not treat readable pages as approved automated feeds. This is an unverified-access finding, not a claim that an interface cannot exist. |
| Username and breach-search directories | The repository also lists services centered on usernames and leaked data. | Lower relevance to the actor/campaign map. A matching username alone is insufficient actor attribution. |

## Fit with the existing dashboard

Code inspection found a CISA **KEV catalog** collector in `backend/connectors/cisa.py`, a UK NCSC advisory collector in `backend/connectors/ncsc.py`, and RIPEstat routing/IODA outage providers in `backend/advanced/providers.py`. CISA KEV additions are historical vulnerability catalog entries, not current attack observations. None supplies a complete actor/campaign knowledge graph.

`backend/advanced/processing.py` currently extracts country and selected institution references, plus cyber indicators. It creates **co_mentioned** edges. `ResolveInput` in `backend/advanced/schemas.py` has no dedicated threat actor, campaign, malware or technique type. Adding feeds alone will therefore improve search coverage but will not create the requested actor intelligence automatically.

The recommended implementation order is:

1. Import MISP actor reference data with stable identifiers and source references; add dedicated actor types, aliases, catalog versioning and conflict handling. Keep catalog updates separate from dated incidents.
2. Add MITRE STIX objects and explicit relationships, retaining source IDs, citations, revoked/deprecated state and source modification dates. Reuse shared actor IDs where documented; do not merge overlapping vendor groups solely by a similar name.
3. Collect SANS diary metadata and bounded API observations. Add Citizen Lab and Krebs feed metadata for fresh reporting. Keep reported occurrence dates separate from publication and retrieval times.
4. Link a report to an actor by an explicit name/alias match and retain the source text supporting it. Create operational edges only when a report supports that relationship. An ambiguous alias match remains a candidate, and a shared mention remains co_mentioned.
5. Add graph paths such as actor → campaign → malware/technique and campaign → affected organization/country. Each edge needs provenance, confidence, relationship meaning and relevant dates.

For the map, distinguish **reported victim location**, **suspected sponsor association**, **IP infrastructure country**, **publisher location** and **country mentioned in text**. Country centroids are contextual geography. Do not animate every catalog group as a new attack, turn a catalog revision date into an incident date, or infer attack routes from country co-mentions. A heatmap should state whether it counts dated reports, observed network activity or historical catalog associations.

Suggested local collection intervals are one day for reference catalogs and 30–60 minutes for report feeds, with conditional requests, bounded items, deduplication and provider-specific backoff. These are implementation recommendations, not claims about provider rate-limit guarantees. No new keys are needed for the public endpoints that passed these checks.

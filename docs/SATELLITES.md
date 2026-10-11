# Satellites and ISS

The orbital overlay prioritises publicly tracked military spacecraft and crewed stations. The snapshot verified on 11 October 2026 contained **127 spacecraft: 82 military, 30 navigation, 13 civil/science and two stations**. Availability changes with the age of published elements; these counts are not a promise of complete military coverage or operational status.

Military families include SAR-Lupe/SARah, CERES, CSO/Helios, Skynet, Syracuse, WGS, AEHF, MUOS, Milstar, GSAT-7, SDA Praetorian, Sapphire and VICTUS HAZE. Selected observer-identified NOSS, FIA Radar, IGS and STSS payloads are also included. Rocket bodies and debris are excluded. Mission descriptions, operator countries and reference links are defined in `backend/orbital_catalog.py`. Unidentified military catalogue entries retain an unknown operator; their missions are not guessed.

## Display

The default **Military & stations** scope includes the ISS and Tiangong. **Military only**, **All spacecraft** and **Navigation · dual use** are selectable beneath the layer switch. GPS spacecraft are described as dual use, rather than counted as exclusively military.

Each map label places its **name before its country flag**. Long catalogue names use compact aliases, such as SDA 601; hover panels and cards retain full names. Labels yield when they would overlap, while the spacecraft icons remain visible. Flags are drawn locally, avoiding external image requests and Windows emoji-font differences.

Origin means the spacecraft's **operator/programme country**, not its current ground position, launch site or manufacturer. International collaborations such as the ISS and Hubble use a globe and list their operators. Unknown origins use a question mark. Observer identifications are labelled separately from official public mission descriptions.

Hover shows the mission, country, operator, catalogue ID, altitude, speed, period, inclination, element age, tracking basis and source. Clicking opens the full detail card and mission reference. Military icons and tracks use amber, navigation blue, and civil/station spacecraft violet; the ISS has its own white icon.

Faint ground tracks cover the preceding 15 and following 90 minutes, sampled every 90 seconds. Hover highlights one spacecraft's track. Tracks split at the dateline, avoiding misleading chords across the world. They can be switched off independently and follow the same scope, search and geographic filters as the icons. These are ground tracks, not surveillance footprints or evidence of a target.

## Public collection

No account, API key or paid service is required. The collector reads public downloads:

| Source                                                                                       | Selection                                                |
| -------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| [CelesTrak visual](https://celestrak.org/NORAD/elements/gp.php?GROUP=visual&FORMAT=json)     | Curated named spacecraft and stations                    |
| [CelesTrak military](https://celestrak.org/NORAD/elements/gp.php?GROUP=military&FORMAT=json) | Payloads in the public military catalogue                |
| [CelesTrak GEO](https://celestrak.org/NORAD/elements/gp.php?GROUP=geo&FORMAT=json)           | Recognised military communication families               |
| [CelesTrak GPS](https://celestrak.org/NORAD/elements/gp.php?GROUP=gps-ops&FORMAT=json)       | Dual-use navigation spacecraft                           |
| [AMSAT](https://www.amsat.org/tle/current/nasabare.txt)                                      | Curated named spacecraft                                 |
| [McCants observers](https://www.mmccants.org/tles/)                                          | Selected observer-identified payloads from `classfd.zip` |

CelesTrak OMM JSON supports six-digit catalogue identifiers, alongside legacy TLE downloads from other providers. Downloads are cached for six hours, exceeding the two-hour interval in [CelesTrak's usage policy](https://celestrak.org/usage-policy.php). HTTP rejections suspend that URL until intervention or a source URL change; other failures preserve the last good elements and defer retries. Responses and decompressed entries are limited to 2 MiB. Epochs, checksums where applicable, catalogue identifiers and orbital parameters are validated. Elements older than 14 days or more than one day in the future are rejected during collection. The newest valid epoch wins across providers.

The normal source worker and dedicated threat gatherer schedule collection under a shared database lease. A single pass is available with `python -m scripts.collect_orbits`; it opens no server port. Existing resident collectors need to load the updated code during the next deployment/reload to adopt the expanded feeds.

The snapshot `public/orbital-elements.json` is disposable runtime data excluded from Git. Development reads it directly; the provided nginx configuration exposes this one public file without exposing the private data directory.

## Position estimates and performance

[Satellite.js](https://github.com/shashwatak/satellite-js) propagates OMM/TLE elements using SGP4, including Earth rotation. Positions refresh locally every two seconds while the layer and page are visible. Ground tracks are cached per minute and are not regenerated or sent to the map on every position update. No additional polling is needed for movement.

Positions are estimates from published elements, not live telemetry, classified tasking or exact overflight alerts. Observer-derived elements carry a separate tracking label. Geostationary spacecraft naturally move very little. Country filters select ground points inside the boundary and do not filter spacecraft ownership. Polar positions may lie outside the world overview. Historical playback clears current positions and tracks because satellite history is not retained.

The standalone `scripts/check_satellite_workspace.py` browser check verifies labels, flags, hover details, highlighted tracks, scope controls, ISS motion, trajectory caching and history clearing against an already running dashboard. It performs no server lifecycle actions.

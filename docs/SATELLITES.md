# Satellites and ISS

The Satellites & ISS overlay follows a curated catalogue of 15 named spacecraft: ISS, Tiangong, Hubble, Terra, Aqua, COSMO-SkyMed 1, ALOS-2, SAOCOM 1A/1B, XRISM, QO-100, AO-7, AO-73, RS-44 and LAPAN-A3. The list describes missions, without asserting current operational status. Rocket bodies, debris and uncatalogued objects are excluded.

The collector downloads the normal public [CelesTrak brightest-object element file](https://celestrak.org/NORAD/elements/gp.php?GROUP=visual&FORMAT=tle) and [AMSAT element file](https://www.amsat.org/tle/current/nasabare.txt). It requires no account, paid service or API key. Old CelesTrak `stations.txt` and `visual.txt` links now return 404; the current public download link is used instead. Only known five-digit catalogue IDs are selected from these TLE files; new six-digit objects require OMM support before they can join this catalogue.

Downloads are cached for six hours, exceeding the two-hour minimum in [CelesTrak's usage policy](https://celestrak.org/usage-policy.php). Failed attempts are persisted and held back for the same interval. Responses are limited to 1 MiB; TLE checksums, catalogue identifiers, inclination, mean motion and epochs are validated. The newest available epoch wins when both providers contain the same spacecraft. Failed downloads preserve the last good elements. The browser independently excludes elements more than 14 days from the requested time, impossible altitudes and propagation failures.

The ordinary source worker and the dedicated `scripts.collect_threat_maps --watch` gatherer both schedule orbital downloads, using a shared database lease. Neither opens a new port. The existing gatherer runs an hourly cache check in its own lane, while cyber sampling keeps its ten-second schedule. A single download pass is also available with `python -m scripts.collect_orbits`.

The resulting `public/orbital-elements.json` is disposable runtime data, excluded from Git. The development dashboard reads this file directly. The provided nginx configuration maps that one public file explicitly for deployed dashboards; it does not expose the private data directory.

[Satellite.js](https://github.com/shashwatak/satellite-js) propagates the orbital elements with SGP4 and converts Earth-centred inertial positions to geodetic coordinates. Calculated ground positions refresh every two seconds while the page is visible and the layer is enabled. Cards and hover details show altitude in kilometres, orbital speed in kilometres per second, catalogue ID, mission, period and source epoch. The ISS gets a separate icon and label.

Positions are estimates, not direct telemetry, exact overflight alerts or tasking evidence. Earth rotation is accounted for in the longitude conversion. Geostationary craft naturally appear almost stationary. Country filters mean the sub-satellite ground point lies within the selected boundary, never that the spacecraft belongs to that country. The layer is independent of event time ranges and is hidden during historical playback; it does not invent historical observations.

Display Overlays uses a separate local concept-and-synonym search to discover layers by topic. It does not call a language model, generate an answer or search event evidence. The main search and Investigate workspace continue to search stored evidence.

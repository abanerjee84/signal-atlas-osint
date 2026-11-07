# ShadowBroker-style monitoring in Signal Atlas

Signal Atlas already has a collection worker, source provenance, MapLibre, OpenSky aircraft, AIS vessels, public orbital elements, conflict reporting, cyber observations and investigation cases. This change adds the missing monitoring workflow at `/monitoring.html`. It implements new code within the existing architecture; it does not import ShadowBroker source code.

## Capability review

| Requested capability | Existing foundation | Implemented enhancement and limits |
| --- | --- | --- |
| Real-time global monitoring | Separate Python worker and FastAPI reads | A dedicated workspace refreshes retained observations every 15 seconds while visible. Upstream sources keep their own collection intervals. |
| 40+ map layers | Broad event categories and reference overlays | 43 overlapping observation sublayers, four orbital views and five reference overlays. Wording filters identify report topics, not independently verified incidents. |
| 60+ feeds | Existing registry of publisher, government, discussion and specialist adapters | Catalog reports actual registered sources, recent successful collection and access requirements. A default configuration had 190 registered source definitions during verification; this is not 190 working or independent feeds. |
| ADS-B aircraft | OpenSky snapshots, filters, measured flight details | Each collected snapshot also writes immutable monitoring history. An optional accuracy feed accepts normalized ADS-B or readsb/dump1090 JSON. OpenSky collection remains demand-driven when the aircraft layer is visible. |
| AIS vessels | Existing public/configured AIS connectors | Position history survives replacement or deletion of the live fleet. The original maritime enrichment work remains intact. |
| Satellites and ground stations | Public elements and browser SGP4 propagation | SatNOGS ground-station directory, separate orbital views and archived element sets for playback. Orbital positions remain calculated estimates. |
| Military and conflict | Existing defence and conflict collectors | Selectable reporting views for drones, missiles, airstrikes, artillery, naval activity, exercises, deployments, ceasefires and evacuation wording. |
| CCTV | No camera directory | TfL JamCam metadata, original source links and opt-in public MP4 playback. Only metadata is retained. No claim that a listed camera works. |
| Radio | No receiver directory | Operator-configured public receiver locations and links. Tuning happens at the receiver's public interface; audio is not collected or archived. |
| GPS jamming | OpenSky does not expose NACp | A GNSS accuracy overlay uses explicit NACp from a configured authorized ADS-B source. Degraded accuracy is a possible interference signal, not confirmation of jamming or its origin. |
| Shodan, malware and C2 | Existing ThreatFox, DShield, honeypot and threat-report integrations | Authenticated passive Shodan public-IP lookup with a server-only key, a UTC daily budget, 24-hour successful-response cache and one-minute retry suppression. New malware/C2 sublayers reuse retained provider evidence. No active scanning. |
| Time Machine | Event-period filtering; live rows could be overwritten | Immutable observation versions, UTC scrubber, five-minute playback steps, receipt-time cutoff, stale markers, retained orbital elements and explicit coverage limits. |

The 15-second UI refresh does not increase source collection frequency. Directory sources refresh hourly; the accuracy feed is polled every 60 seconds and maritime every five minutes. Accuracy and maritime collection have independent polling tasks alongside the existing demand-driven OpenSky lane, so a slow batch of news feeds does not hold them in its queue. Existing source controls, commercial-use permission decisions, request limits, outbound host validation and bounded payloads still apply.

## Run

1. Restart the API and worker so migration `012_monitoring_history.sql` and the new collectors load. Use the existing `START.bat` workflow on Windows.
2. Open the dashboard's **Monitor** link, or visit `http://127.0.0.1:5173/monitoring.html`.
3. Inspect **Source health**. TfL and SatNOGS need no configured key. Access-dependent sources state what is missing.
4. Enable layers and inspect points or feed rows. Unlocated observations stay in the feed. A response is capped at 2,000 records in the UI; select fewer layers when the cap is reported.
5. Load a UTC timestamp, drag the history scrubber or select **Play history**. **Live** resumes current reads. Playback starts at the first retained receipt and advances five minutes every two seconds; it does not interpolate missing observations.

New history starts when the updated collector runs. Existing event rows are not backdated into the new history. Delayed reports enter playback only after their local receipt time. The latest version per source/entity is selected before layer filtering, so an aircraft that landed does not reappear from an earlier airborne observation. Observation times and receipt times are shown separately.

## Configuration

```dotenv
OSINT_MONITORING_RETENTION_DAYS=7
OSINT_MONITORING_MAX_ROWS=250000
OSINT_TFL_CAMERAS_ENABLED=true
OSINT_SATNOGS_STATIONS_ENABLED=true
OSINT_PUBLIC_RADIO_RECEIVERS=[]
OSINT_MONITORING_ADSB_URL=
OSINT_SHODAN_API_KEY=
OSINT_SHODAN_DAILY_BUDGET=20
```

Maintenance removes observations older than the configured receipt age and retains at most the configured row count. These limits are applied during the existing maintenance cycle, not on every insert. High-volume aircraft/vessel collection can shorten the available time span below seven days. Original event/raw-record retention remains separate. History has no foreign key to current event rows, so fleet replacement does not cascade into the archive.

Public radio configuration accepts an array of objects with `id`, `name`, `latitude`, `longitude`, `url` and optional `bands`. Add only receivers whose operators publish access. These are configured reference links, not automatically discovered private radios. No example receivers are seeded.

The optional ADS-B URL must use an authorized public endpoint. Add its exact DNS name to `OSINT_EXTRA_ALLOWED_HOSTS`; the usual SSRF protection rejects private/internal addresses. For normalized JSON, provide this schema (the values below are illustrative, not a real aircraft observation):

```json
{
  "aircraft": [{
    "icao24": "abc123",
    "observed_at": "2026-11-01T12:00:00Z",
    "latitude": 51.5,
    "longitude": -0.1,
    "nac_p": 3,
    "on_ground": false,
    "source_url": "https://provider.example/observations"
  }]
}
```

Standard readsb/dump1090 `aircraft.json` is also accepted, using the root `now`, and each aircraft's `hex`, `lat`, `lon`, `seen_pos`, `nac_p` and `alt_baro`. Position age must be present, finite and no more than 900 seconds. Normalized rows require a timezone-aware observation time; future fixes, invalid ICAO IDs, invalid NACp and non-boolean ground status are rejected. Provider credentials remain in server configuration; they must not be included in `source_url`.

GNSS cells are one degree square. Each cell needs three distinct airborne aircraft with known NACp 1–11. NACp 1–4 counts as low accuracy. NACp 0, missing accuracy, grounded aircraft and stale fixes are excluded. Multiple providers reporting the same transponder count once, using the newest eligible observation. The ratio describes this sample only; a capped response is labelled as incomplete. No emitter or intentional cause is inferred.

Set both `OSINT_ADMIN_TOKEN` and `OSINT_SHODAN_API_KEY` for Shodan. Enter the local token in the monitoring form; the page keeps it only in the input, without persistent storage. Requests ask Shodan for existing minified host records. No target address is contacted. Failed upstream calls consume the local daily request budget; upstream exception strings and request URLs are not returned. API-key-free deployment leaves the function unavailable with a setup message.

For Nginx deployments, rebuild the frontend and reload the updated headers snippet. Its `media-src` permits TfL's existing public JamCam bucket for opt-in video. Radio pages open in a separate tab. Camera URLs during playback point to current provider content and are labelled accordingly; footage and audio are not historical evidence.

## API and storage

| Endpoint | Purpose |
| --- | --- |
| `GET /api/monitoring/catalog` | Observation-layer catalog, registered source health and actual history bounds |
| `GET /api/monitoring/frame?at=<ISO-8601>&hours=24&layers=aircraft,vessels&limit=2000` | Latest retained observation per source/entity known at the selected time; include `gnss` for derived accuracy cells |
| `GET /api/monitoring/orbits?at=<ISO-8601>` | Latest orbital element snapshot retained at or before the selected time |
| `POST /api/monitoring/shodan` with `{"ip":"8.8.8.8"}` | Protected passive public-IP lookup |

`at` must include a timezone and cannot be future-dated. Frame windows accept 1–168 hours and responses accept 1–5,000 observations. Unknown layer IDs are rejected. Responses state truncation, source, location precision, observation time, receipt time and stale state. Live orbital reads can use the existing local element file; historical reads require an archived element snapshot and never fall back to newer elements. Reference overlays always use the published current registry version and are excluded from observation counts.

Migration 012 adds `monitoring_history`, `monitoring_orbits` and `monitoring_lookups`. Observation capture is inside the existing database ingestion transaction; the live OpenSky path also captures snapshots independently of its half-hour event-history cadence. Sensor directories use a separate `sensors` classification and write directly to monitoring history, keeping reference metadata out of incident counts, country activity and reporting alerts. The orbital collector archives the element set when it becomes locally known, preserving individual source timestamps and orbital epochs.

## Verification

New tests cover immutable revisions and deduplication, receipt cutoffs, future timestamps, vessel replacement, aircraft movement between event snapshots, latest-state layer filtering, unique GNSS samples, sensor validation, API bounds, auth, cached/budgeted Shodan responses, redacted provider failures and retention. Browser checks cover layer selection, inspection, UTC playback, live return, source credentials, empty history, mobile layout and recoverable errors.

Live public-source verification in an isolated database fetched and retained 889 TfL camera records with zero rejected records. SatNOGS returned 4,563 station records; the configured per-source cap retained 1,000, with zero rejected records and 3,563 explicitly reported as truncated. This verifies directory ingestion, not live camera availability, station connectivity, global sensor coverage or paid provider access.

Build, lint, 14 new backend tests, three new browser tests and the selected compatibility checks passed. Three existing dashboard browser cases also failed with the original dashboard markup. An additional full backend sweep was stopped during a slow telemetry-retention stress test after earlier failures; it is not counted as a passing full suite. See [verification results](monitoring-verification.json) for the exact scopes and remaining live-provider checks.

## Primary references

- [ShadowBroker project](https://github.com/BigBodyCobain/Shadowbroker): capability comparison, not an imported dependency.
- [TfL Unified API](https://api.tfl.gov.uk/): public `Place/Type/JamCam` endpoint and provider terms.
- [SatNOGS Network API](https://network.satnogs.org/api/): public station directory.
- [Shodan host API](https://developer.shodan.io/api): passive host lookup and `minify` response option.
- [readsb JSON format](https://github.com/wiedehopf/readsb/blob/dev/README-json.md): aircraft accuracy and position-age fields.

# Operations and recovery

## Inspect the running system

`GET /api/health` checks that the API can query its database. It does not imply every external source is working. `/api/status` shows connector states, current errors, last success, stale flags, storage size and worker heartbeat. `/api/ai/usage` shows local UTC-day attempts, token accounting and credential configuration without exposing secrets.

```bash
sudo systemctl status osint-api osint-worker
sudo journalctl -u osint-worker -n 100 --no-pager
sudo journalctl -u osint-api -n 100 --no-pager
sudo systemctl list-timers 'osint-*'
sudo systemctl show osint-api osint-worker -p MemoryCurrent -p MemoryPeak
df -h /var/lib/osint
```

The resource-monitor timer writes a structured disk snapshot every 15 minutes and exits with failure below the 1 GiB default free-space reserve. Set `OSINT_DISK_RESERVE_BYTES` in the service environment to change that threshold. A failed timer/service must be connected to your site's alerting if unattended notification is required; this application does not send messages to an external service automatically.

## Common conditions

| Condition | Check and action |
| --- | --- |
| Empty map | Check period, selected layers and map extent. Unlocated records stay in the unrestricted event list. Inspect source health. A new installation contains no intelligence until ingestion succeeds. |
| API unavailable | Inspect `osint-api` journal, database permissions, absolute database path and port 8000. Nginx should proxy the path unchanged. Restart after correcting configuration. |
| Map background without countries/points | Verify `countries.geojson` and the hashed MapLibre `.mjs` worker are served. The worker needs a JavaScript MIME type. Check the browser console for CSP/worker errors. Do not remove the worker from the built `dist/` tree. |
| Collector inactive | Inspect worker service and heartbeat. Run one source with `python -m backend.worker --once --source usgs` under the configured environment to isolate it. Avoid running multiple scheduled workers. |
| Provider HTTP 429 | Retain last successful records and wait for the scheduled retry. Lower collection frequency if needed. Repeated page refresh does not collect providers or run AI. |
| Access required | Supply authorized backend credentials or approved app name. Restart the API/worker. Adapter existence is not evidence of live access. |
| Provider HTTP 401/403 | Check credentials, access permissions and provider policy. Do not bypass authentication. Tokens are obtained at each scheduled credentialed collection, avoiding persistent expired OAuth tokens. |
| NATO HTTP 404 | Legacy RSS endpoint is unavailable. Use the verified UK MOD feed or configure another permitted military feed. |
| All records rejected | Provider format may have changed. Inspect source schema against the connector and reproduce using a redacted fixture. Rejected content is not placed on the map. |
| FIRMS response exceeds size bound | Narrow its bbox. A world VIIRS feed can contain many detections. Configure a properly rate-accounted tiling adapter before requesting exhaustive coverage. |
| Protected functions unavailable | Set a long `OSINT_ADMIN_TOKEN` on the server, restart, then enter that token in browser Settings. It is distinct from the OpenRouter/provider key. |
| Free model unavailable | Inspect current OpenRouter catalogue, choose a zero-price available model and optional free fallback. The server refuses a priced model while free-only mode is enabled. |
| Local AI budget exhausted | Budget counts every outbound completion attempt, including retries and errors, and resets at UTC midnight. Cached analyses remain available. Avoid raising the budget above the provider account allowance. |
| AI schema/citation rejection | The response was discarded. Inspect source records and model capability; no malformed output is saved as successful analysis. A valid citation still needs analyst fact-checking. |
| SQLite busy/write failure | Verify free disk space, one collection worker, path permissions and other database processes. Busy timeout is 10 seconds. Do not copy a live WAL file as a backup or delete it to clear a lock. |
| TLS certificate failure | Fix the installed trust chain or use a protected `SSL_CERT_FILE` trust bundle. Runtime HTTPX uses the OS trust store. Never disable certificate verification. |

Source states never clear stored records on a fetch failure. API and map remain usable with previously retained data. Refreshing the dashboard only reads the database. An authenticated source-health action can request one collector run; it does not overlap an active job or solve provider access limits.

## Maintenance and disk sizing

The worker runs retention and SQLite optimization hourly. You can also run `scripts/maintenance.py` under the configured service environment or call the protected `/api/admin/maintenance` endpoint. It expires raw payloads, normalized events and cascading reports/reviews, daily statistics and AI caches according to configuration. It performs a passive WAL checkpoint and query planner optimization.

The isolated 10,000-record benchmark produced a 28,094,464-byte database using synthetic records with short raw payloads. This is a measurement for that fixture, not a per-event storage guarantee. Real raw metadata, supporting reports, tracking frequency and backups change storage costs. Measure the intended event/report rate before enabling large aviation, maritime or fire regions. Bound each feed, forecast retained volume and reserve space for WAL and backups. PostgreSQL/PostGIS is an upgrade option when SQLite write concurrency or indexed geospatial analysis is demonstrably insufficient; it is not required for this initial dataset.

Hourly maintenance does not reclaim every freed database page immediately. Run a full SQLite `VACUUM` only during a maintenance window with sufficient spare disk and stopped writes; it can require a temporary copy of the database. No automatic full vacuum runs on every poll.

## Online backup

Backups now include active media in a SHA-256-verified bundle alongside the consistent database. Configure `OSINT_EVIDENCE_DIRECTORY=/var/lib/osint/evidence` on Ubuntu. See [advanced recovery instructions](ADVANCED_OSINT.md#backup-and-recovery), including the new-directory-only restore command and the existing exclusion of bulk public discussion snapshots.

The daily timer uses SQLite's online backup API and checks integrity. It keeps seven copies by default with restrictive permissions. The CLI is usable locally as well:

```bash
cd /opt/osint
# Run with the same protected environment as the services.
.venv/bin/python scripts/backup.py --destination /var/backups/osint --keep 7
```

Loading `/etc/osint/osint.env` is required for standalone operational commands; the systemd jobs load it automatically. To avoid shell parsing surprises, use an administrator-controlled service invocation or export the specific required `OSINT_DATABASE` variable for a direct backup command. Do not print or broadly dump credential-bearing environment files.

Backups contain source records, raw payloads and cached analysis. Store any off-host copies according to provider licensing. Schedule off-host transfer using your existing backup system; this project has no external storage credentials or automatic upload.

## Restore

Test in an isolated directory before changing production. Use a backup generated by the online backup tool. Check `PRAGMA integrity_check`, schema version and source/event counts with the matching application version. Automated tests cover backup integrity and restored source details.

For production recovery, stop API and worker, preserve the current database and its WAL/SHM files as a dated recovery bundle, and restore the chosen backup to `/var/lib/osint/osint.sqlite3` with `osint:osint` ownership and mode 0600. Move aside any old WAL/SHM sidecars while services are stopped; never attach a previous database's sidecars to the restored backup. Restart services and verify health, source details and collector recovery. Do not overwrite the only recovery copy.

## Soak test record

Use at least a representative 24-hour period on the actual 8 GB Ubuntu host. Record per-process RSS/peak and trend, ingest rate and rejected records, API latency samples, SQLite/WAL/disk sizes, job overlap, stale sources, source request limits and restart/network outage behavior. Plot RSS over time rather than relying on one initial reading. The short Windows regression benchmark cannot establish absence of a slow leak. Save the measurements with hardware and configuration in `docs/` before declaring Phase 6 accepted.

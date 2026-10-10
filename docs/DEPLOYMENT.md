# Ubuntu deployment

Target: Ubuntu 24.04 LTS with Python 3.12, 8 GB RAM, a DNS name and valid TLS certificate. This guide and service files have been authored and reviewed on Windows; they have not been executed on the target Ubuntu hardware. Production acceptance requires the checks at the end of this document.

## Build and install

Install OS packages using your server administration account:

```bash
sudo apt update
sudo apt install python3 python3-venv nginx certbot rsync
sudo useradd --system --home /var/lib/osint --shell /usr/sbin/nologin osint
sudo install -d -o root -g root -m 0755 /opt/osint
sudo install -d -o osint -g osint -m 0700 /var/lib/osint /var/backups/osint
sudo install -d -o root -g osint -m 0750 /etc/osint
```

If the `osint` account already exists, inspect it and reuse it rather than rerunning account creation. Copy the source tree to `/opt/osint`. Exclude `.env`, local data, `.venv`, `node_modules`, test results and logs. Keep the country GeoJSON and its license. Never move the Windows virtual environment to Linux.

Use an installed Node.js 22.12+ or 24+ build runtime to create `dist/` from the pinned npm lockfile. The deployed service does not require Node or Vite to run. Alternatively, build on the workstation and transfer the entire `dist/` directory, including the MapLibre `.mjs` worker and `countries.geojson`.

```bash
cd /opt/osint
npm ci
npm run build
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
sudo chown -R root:root /opt/osint
sudo install -o root -g osint -m 0640 .env.example /etc/osint/osint.env
sudoedit /etc/osint/osint.env
```

Set `OSINT_DATABASE=/var/lib/osint/osint.sqlite3`. Generate a protected access token with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'` and copy it into `OSINT_ADMIN_TOKEN` using the editor. Keep the token out of shell history and repository files. Supply provider credentials only when you have appropriate access. Empty OpenRouter credentials leave the rest of the application usable.

Install service and timer files:

```bash
sudo install -m 0644 deploy/osint-*.service deploy/osint-*.timer /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/osint-*.service /etc/systemd/system/osint-*.timer
sudo systemctl daemon-reload
sudo systemctl enable --now osint-api osint-worker osint-backup.timer osint-monitor.timer
curl --fail http://127.0.0.1:8000/api/health
```

Both resident services use one process and a 512 MiB memory ceiling each. They run under the dedicated account with a private temporary directory, read-only system paths and a 0077 file-creation mask. Only `/var/lib/osint` is writable. The backup job can also write `/var/backups/osint`. Verify these paths before changing service confinement. The collector bounds concurrency to two by default.

## HTTPS and reverse proxy

Replace `osint.example.org` in both Nginx files with your DNS name. This is a placeholder, not a deployment destination. Point DNS to the server and make ports 80/443 reachable. Port 8000 remains bound to localhost. Restrict SSH according to your server's access policy.

Install the bootstrap configuration, which exposes only the certificate challenge and returns 503 elsewhere:

```bash
sudo install -d -m 0755 /var/www/acme
sudo install -m 0644 deploy/nginx-bootstrap.conf /etc/nginx/sites-available/osint
sudo ln -s /etc/nginx/sites-available/osint /etc/nginx/sites-enabled/osint
sudo nginx -t
sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/www/acme -d YOUR_DOMAIN
```

If a site symlink already exists, inspect it and keep it instead of recreating it. Replace `YOUR_DOMAIN` in the certificate command with the same actual DNS name. Certificate issuance requires domain control; it was not performed during local development.

Once the certificate exists, install the HTTPS site and common security headers:

```bash
sudo install -m 0644 deploy/nginx-headers.conf /etc/nginx/snippets/osint-headers.conf
sudo install -m 0644 deploy/nginx.conf /etc/nginx/sites-available/osint
sudo nginx -t
sudo systemctl reload nginx
curl --fail https://YOUR_DOMAIN/api/health
sudo certbot renew --dry-run
```

Keep the challenge location for renewal. The configuration redirects HTTP to HTTPS, serves compiled assets, provides a JavaScript MIME type for `.mjs` module workers, proxies `/api/`, sets security headers and applies separate AI/general rate limits. The deployment CSP allows local scripts, local/blob workers, WASM evaluation and dynamic styles required by the libraries. A production-bundle browser test exercises this policy locally. Live Nginx syntax, certificate chain and renewal must still be checked on Ubuntu. See the [Nginx HTTPS](https://nginx.org/en/docs/http/configuring_https_servers.html) and [rate-limit module](https://nginx.org/en/docs/http/ngx_http_limit_req_module.html) documentation for directive behavior.

The API's built-in documentation uses CDN assets and should be accessed through localhost or a separate trusted development policy; the strict production CSP intentionally does not load those external docs assets. `/api/openapi.json` remains available for a local API viewer.

## Logs, upgrades and rollback

The API logs to the system journal. The worker emits JSON collection results. HTTPX request logging is suppressed for the worker so URL-embedded provider credentials cannot enter normal logs. Do not enable debug HTTP logging on credentialed collectors. Nginx uses its standard Ubuntu log rotation. `deploy/journald-osint.conf` supplies an optional 256 MiB/14-day system-wide journal budget; review its effect on other services before installing it as a journal drop-in.

Before an upgrade, create a consistent backup, stop the worker and API, preserve the old source/build and dependency lockfiles, install the new version, and restart. Schema migrations run during application initialization. Version 1 to 2 is covered by automated tests. Migrations currently have no automatic downgrade; rollback across schema changes requires the corresponding backup and application version. Do not run `pip install` while the API is serving requests.

## Target acceptance

Record hardware, OS/package versions, event/report counts, connection speed and client/browser hardware. Then verify:

1. `nginx -t`, unit verification, certificate validation and renewal.
2. Dashboard, geographic filters, all panel controls and source traceability through the public hostname.
3. One real successful collection for every enabled source; unauthorized sources stay disabled/access-required.
4. A protected live OpenRouter request, supporting IDs, cache reuse, exhausted local/provider quotas and timeout recovery.
5. `systemctl restart` for both resident services; job state and stored data recover.
6. A network outage and recovery without deleting the last successful feed records.
7. Online backup, integrity check and restore into an isolated directory before any replacement of production data.
8. At least a representative 24-hour soak: journal errors, RSS trends, SQLite/WAL size, disk reserve, request p95 and sustained ingestion.
9. Initial page load below four seconds on the defined connection, cached query p95 below 500 ms and representative map interaction at 30 FPS or more.

The Windows benchmark does not satisfy this target-hardware acceptance. Keep resource ceilings and record bounds until measurements justify changing them.

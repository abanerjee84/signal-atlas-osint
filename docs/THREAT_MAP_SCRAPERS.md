# Public threat map scrapers

Inspection date: 11 October 2026. The Python adapters in `backend/connectors/threat_maps.py` read the public transports used by the requested maps. They run bounded collection jobs in the existing collector, require no credentials and do not create a server.

| Site | Observed delivery | Result on this host |
| --- | --- | --- |
| [BunkerWeb threat map](https://www.bunkerweb.io/threatmap/) | Its public page configures `https://threatmap.bunkerweb.io`; its [map script](https://www.bunkerweb.io/wp-content/uploads/threatmap/js/datamap.main.js) subscribes to `/stream` using EventSource. | Ordinary HTTPS returned 200 and `text/event-stream`. Real country-pair detections were collected and stored. |
| [Bitdefender threat map](https://threatmap.bitdefender.com/) | Its [public client](https://threatmap.bitdefender.com/js/ws.js) subscribes to 13 channels through Socket.IO. Browser requests use `/socket.io/?EIO=3&transport=polling`. | Browser and Python requests returned plain `ok` instead of the required Engine.IO handshake. The collector reports that failure. No live Bitdefender observations could be verified. |

The Bitdefender collector decodes Engine.IO v3 text framing, including JavaScript UTF-16 lengths, reads a valid session handshake, subscribes to the site's published channels and processes `ev` batches. This protocol path is covered by synthetic transport tests in temporary databases. It has not been verified against a working live feed because the provider transport was unavailable. No simulation functions from the provider's JavaScript are used.

BunkerWeb sends `attacker`, `target`, `reason` and `date` fields. Its use of the word “attacker” does not establish human attribution: the adapter records **traffic origin country**, destination and the provider's blocking reason. Bitdefender's public rendering code distinguishes `from`/`to` geography from a single `loc` detection; the collector preserves that distinction when the stream works. Location-only detections create no directed route.

## Sampling and time

Each job reads at most 20 seconds of stream traffic and stores at most 100 observations, also respecting the global record limit. The data-gathering thread fires every **120 seconds**, measured from the start of each cycle. Provider errors and throttling respect persisted backoff; a cycle can skip a source until its deadline. The window samples provider coverage; it misses events outside the collection window and cannot estimate worldwide attack volume. There is no fabricated replay or extrapolated packet timing.

BunkerWeb's observed `date` is a time of day without an established date or timezone. It is retained as an opaque provider timestamp. Occurrence time remains unknown; the timeline uses the observation's receipt time, labelled in its details. Bitdefender numeric timestamps follow its `moment(evt.ts)` millisecond interpretation; invalid or future timestamps remain unknown. Receipt time remains separate.

Observation IDs identify individual deliveries within a bounded collection, not unique verified attacks. The same attack can generate multiple requests, and upstream replay cannot be ruled out when no unique event ID is supplied. Routes aggregate observations by provider, reason and country pair. Identical report URLs are deduplicated separately from telemetry.

## Location and attribution

Country references use illustrative Natural Earth label coordinates. The bundled 1:110m polygons omit small countries including Singapore. A separate public-domain [reference point file](../public/country-context.geojson) supplies 64 omitted countries/territories from Natural Earth's 1:10m data; it adds no boundary polygons. [Source and downloaded-file checksum](../public/COUNTRY_CONTEXT_LICENSE.txt) are retained. Unsupported country codes remain unknown, and missing coordinates never become `(0, 0)`.

Telemetry records have `actor="Unknown actor"`, no attributed attacker country and no confirmed victim-country role. Traffic geography, observed detections and published attribution remain separate model fields. No human identity is inferred from an IP, publisher, actor alias or infrastructure country.

## Collection controls

- Only approved public HTTPS destinations and ports are read. Robots policies are checked. Redirects in robots reads are bounded and every hop is validated; stream redirects are rejected.
- Response bytes, line sizes, record count and sample duration are bounded. Streams close on cancellation or reaching the sampling bound. Denials and throttling stop collection and appear in source health.
- Only whitelisted country, type/reason and timing fields are stored. Upstream IPs, URLs of attacked resources, socket session identifiers and arbitrary payload fields are discarded.
- Per-source telemetry history is capped at 2,000 observations and seven days, independent of the published report retention. Deleting old observations cascades to their stored reports and raw records. Previously collected samples remain visible after a provider error.
- TLS verification stays enabled. No login cookies, proxies, CAPTCHA solving, guarded endpoints or access-control bypass are used. Ordinary public access does not grant unrestricted republication rights; provider terms apply.

To collect once against an already initialized application database:

```powershell
.\.venv\Scripts\python.exe -m scripts.collect_public_updates --source bunkerweb_threatmap --source bitdefender_threatmap
```

The command respects persisted deadlines and locks, writes only real observations and safe aggregate health, and exits. It does not start or stop any server.

For the requested gathering thread against the existing database:

```powershell
.\.venv\Scripts\python.exe -m scripts.collect_threat_maps --watch
```

This collector opens no listening port. A renewable database lease prevents duplicate gathering processes. Its local heartbeat is written to ignored `data/run/threat-map-thread.json`; the dashboard reads an ignored aggregate health bridge at `public/threatmap-status.json`. Status updates use atomic replacement with bounded retries for Windows reader locks. Only the disposable public bridge permits an in-place fallback if a persistent reader prevents deletion; the UI treats a concurrent JSON parse failure as unavailable. The background instance was launched hidden with `pythonw.exe` on this host at the user's request; it does not install a startup task or survive a machine restart. The normal application worker also uses the two-minute source interval after its next user-controlled reload. Existing servers were left untouched.

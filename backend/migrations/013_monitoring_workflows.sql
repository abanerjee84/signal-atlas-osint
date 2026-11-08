-- AUTOINCREMENT keeps watch cursors monotonic even when all history is pruned.
CREATE TABLE monitoring_receipts (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT,
 observation_id TEXT UNIQUE NOT NULL REFERENCES monitoring_history(observation_id) ON DELETE CASCADE
);
INSERT INTO monitoring_receipts(observation_id)
 SELECT observation_id FROM monitoring_history ORDER BY rowid;
CREATE TABLE monitoring_rules (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, config TEXT NOT NULL, created_at TEXT NOT NULL,
 enabled INTEGER NOT NULL DEFAULT 1, cursor INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE monitoring_rule_states (
 rule_id TEXT NOT NULL REFERENCES monitoring_rules(id) ON DELETE CASCADE,
 source_id TEXT NOT NULL, entity_id TEXT NOT NULL, inside INTEGER NOT NULL,
 last_alert TEXT, observed_at TEXT NOT NULL, PRIMARY KEY(rule_id, source_id, entity_id)
);
CREATE TABLE monitoring_alerts (
 id TEXT PRIMARY KEY, rule_id TEXT NOT NULL REFERENCES monitoring_rules(id) ON DELETE CASCADE,
 observation_id TEXT NOT NULL, kind TEXT NOT NULL, triggered_at TEXT NOT NULL,
 snapshot TEXT NOT NULL, acknowledged_at TEXT, UNIQUE(rule_id, observation_id, kind)
);
CREATE INDEX idx_monitoring_alerts_time ON monitoring_alerts(triggered_at DESC);
CREATE TABLE monitoring_assets (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL, entity_id TEXT NOT NULL, version TEXT NOT NULL,
 name TEXT NOT NULL, kind TEXT NOT NULL, geometry TEXT, payload TEXT NOT NULL,
 received_at TEXT NOT NULL, UNIQUE(source_id,entity_id,version)
);
CREATE INDEX idx_monitoring_assets_source ON monitoring_assets(source_id,entity_id,received_at DESC);
CREATE TABLE monitoring_scenes (
 id TEXT PRIMARY KEY, provider TEXT NOT NULL, native_id TEXT NOT NULL, collection TEXT NOT NULL,
 acquired_at TEXT NOT NULL, geometry TEXT, assets TEXT NOT NULL, metadata TEXT NOT NULL,
 received_at TEXT NOT NULL, UNIQUE(provider,native_id)
);
CREATE INDEX idx_monitoring_scenes_time ON monitoring_scenes(acquired_at DESC);
CREATE TABLE monitoring_analyses (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE monitoring_lookup_calls (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, target TEXT NOT NULL, requested_at TEXT NOT NULL,
 payload TEXT, expires_at TEXT
);
CREATE INDEX idx_monitoring_lookup_cache ON monitoring_lookup_calls(kind,target,requested_at DESC);

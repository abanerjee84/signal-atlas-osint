CREATE TABLE monitoring_history (
 observation_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, entity_id TEXT NOT NULL,
 observed_at TEXT NOT NULL, received_at TEXT NOT NULL, category TEXT NOT NULL,
 latitude REAL, longitude REAL, layers TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE INDEX idx_monitoring_time ON monitoring_history(observed_at DESC, received_at);
CREATE INDEX idx_monitoring_received ON monitoring_history(received_at DESC, observation_id);
CREATE INDEX idx_monitoring_entity ON monitoring_history(source_id, entity_id, observed_at DESC);
CREATE TABLE monitoring_lookups (
 cache_key TEXT PRIMARY KEY, requested_at TEXT NOT NULL, payload TEXT
);
CREATE INDEX idx_monitoring_lookup_time ON monitoring_lookups(requested_at);
CREATE TABLE monitoring_orbits (
 collected_at TEXT PRIMARY KEY, payload TEXT NOT NULL
);

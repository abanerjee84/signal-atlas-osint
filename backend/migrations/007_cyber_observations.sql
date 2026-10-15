CREATE TABLE cyber_observations (
 record_id TEXT PRIMARY KEY REFERENCES external_records(record_id) ON DELETE CASCADE,
 indicator_id TEXT NOT NULL REFERENCES cyber_indicators(indicator_id),
 source_id TEXT NOT NULL, source_family TEXT NOT NULL, provider_record_id TEXT NOT NULL,
 kind TEXT NOT NULL, first_seen TEXT, last_seen TEXT, period_start TEXT, period_end TEXT,
 received_at TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(source_id,provider_record_id)
);
CREATE INDEX cyber_observations_indicator ON cyber_observations(indicator_id,received_at DESC);
CREATE INDEX cyber_observations_source ON cyber_observations(source_id,received_at DESC);
CREATE TABLE cyber_ddos_series (
 source_id TEXT NOT NULL, start_at TEXT NOT NULL, end_at TEXT NOT NULL, protocol TEXT NOT NULL,
 percentage REAL NOT NULL CHECK(percentage>=0 AND percentage<=100),
 original_url TEXT NOT NULL, retrieved_at TEXT NOT NULL,
 PRIMARY KEY(source_id,start_at,protocol)
);

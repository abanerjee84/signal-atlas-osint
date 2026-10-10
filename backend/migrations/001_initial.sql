CREATE TABLE events (
 event_id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
 category TEXT NOT NULL, latitude REAL, longitude REAL, location_precision TEXT NOT NULL,
 location_basis TEXT NOT NULL, country_code TEXT, occurred_at TEXT, published_at TEXT NOT NULL,
 ingested_at TEXT NOT NULL, updated_at TEXT NOT NULL, source_id TEXT NOT NULL, source_url TEXT NOT NULL,
 confidence TEXT NOT NULL, evidence_basis TEXT NOT NULL, severity TEXT NOT NULL, severity_basis TEXT NOT NULL,
 tags TEXT NOT NULL, ai_summary TEXT, time_key TEXT NOT NULL
);
CREATE INDEX idx_events_time ON events(time_key DESC);
CREATE INDEX idx_events_category_time ON events(category,time_key DESC);
CREATE INDEX idx_events_country_time ON events(country_code,time_key DESC);
CREATE INDEX idx_events_geo ON events(longitude,latitude);
CREATE INDEX idx_events_published ON events(published_at DESC);
CREATE INDEX idx_events_ingested ON events(ingested_at DESC);
CREATE TABLE reports (
 report_id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
 source_id TEXT NOT NULL, external_id TEXT NOT NULL, source_url TEXT NOT NULL,
 title TEXT NOT NULL, description TEXT NOT NULL, published_at TEXT NOT NULL, occurred_at TEXT,
 ingested_at TEXT NOT NULL, updated_at TEXT NOT NULL, language TEXT NOT NULL,
 sentiment_kind TEXT, sentiment_label TEXT, sentiment_score REAL, metadata TEXT NOT NULL,
 UNIQUE(source_id,external_id)
);
CREATE INDEX idx_reports_event ON reports(event_id);
CREATE INDEX idx_reports_url ON reports(source_url);
CREATE INDEX idx_reports_sentiment ON reports(sentiment_kind,published_at);
CREATE TABLE raw_records(report_id TEXT PRIMARY KEY REFERENCES reports(report_id) ON DELETE CASCADE,
 payload TEXT NOT NULL, ingested_at TEXT NOT NULL);
CREATE TABLE connector_status(source_id TEXT PRIMARY KEY, state TEXT NOT NULL DEFAULT 'never_run',
 last_attempt TEXT, last_success TEXT, error TEXT, fetched INTEGER NOT NULL DEFAULT 0,
 stored INTEGER NOT NULL DEFAULT 0, rejected INTEGER NOT NULL DEFAULT 0, truncated INTEGER NOT NULL DEFAULT 0,
 next_run TEXT, duration_ms REAL);
CREATE TABLE ai_calls(id INTEGER PRIMARY KEY, requested_at TEXT NOT NULL, model TEXT NOT NULL,
 status TEXT NOT NULL, prompt_tokens INTEGER NOT NULL DEFAULT 0, completion_tokens INTEGER NOT NULL DEFAULT 0);
CREATE INDEX idx_ai_calls_time ON ai_calls(requested_at);
CREATE TABLE ai_cache(cache_key TEXT PRIMARY KEY, response TEXT NOT NULL, created_at TEXT NOT NULL,
 expires_at TEXT NOT NULL);
CREATE TABLE daily_stats(day TEXT NOT NULL, category TEXT NOT NULL, count INTEGER NOT NULL,
 PRIMARY KEY(day,category));
CREATE TABLE job_locks(name TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE worker_state(id INTEGER PRIMARY KEY CHECK(id=1), heartbeat TEXT NOT NULL);

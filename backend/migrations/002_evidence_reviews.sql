CREATE TABLE evidence_reviews (
 id INTEGER PRIMARY KEY, event_id TEXT NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
 confidence TEXT NOT NULL, basis TEXT NOT NULL, report_ids TEXT NOT NULL,
 independent_sources_confirmed INTEGER NOT NULL DEFAULT 0,
 contradiction_confirmed INTEGER NOT NULL DEFAULT 0, reviewed_at TEXT NOT NULL
);
CREATE INDEX idx_reviews_event ON evidence_reviews(event_id,id DESC);

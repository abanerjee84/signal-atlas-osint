CREATE TABLE aircraft_snapshot (
 id INTEGER PRIMARY KEY CHECK(id=1), collected_at TEXT NOT NULL,
 history_at TEXT, payload TEXT NOT NULL
);

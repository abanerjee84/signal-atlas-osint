CREATE TABLE sources (
 source_id TEXT PRIMARY KEY, name TEXT NOT NULL, owner TEXT NOT NULL, category TEXT NOT NULL,
 official_url TEXT NOT NULL, integration TEXT NOT NULL, access_class TEXT NOT NULL,
 license_classification TEXT NOT NULL, permissions_state TEXT NOT NULL DEFAULT 'unreviewed',
 enabled INTEGER NOT NULL DEFAULT 0, last_verified_at TEXT, details TEXT NOT NULL
);
CREATE TABLE source_capabilities(source_id TEXT PRIMARY KEY REFERENCES sources(source_id), capabilities TEXT NOT NULL);
CREATE TABLE external_records (
 record_id TEXT PRIMARY KEY, event_id TEXT, source_id TEXT NOT NULL, external_record_id TEXT NOT NULL,
 original_url TEXT NOT NULL, title TEXT NOT NULL, text TEXT NOT NULL, language TEXT NOT NULL,
 kind TEXT, category TEXT NOT NULL, published_at TEXT, observed_at TEXT, ingested_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, last_verified_at TEXT, content_hash TEXT, country TEXT,
 latitude REAL, longitude REAL, precision TEXT NOT NULL, confidence TEXT NOT NULL,
 metadata TEXT NOT NULL, license_classification TEXT NOT NULL DEFAULT 'source_terms', indexed_at TEXT
);
CREATE INDEX aos_records_time ON external_records(published_at DESC);
CREATE INDEX aos_records_source ON external_records(source_id,published_at DESC);
CREATE INDEX aos_records_category ON external_records(category,published_at DESC);
CREATE INDEX aos_records_country ON external_records(country,published_at DESC);
CREATE VIRTUAL TABLE aos_search USING fts5(record_id UNINDEXED,title,text, tokenize='unicode61');
CREATE TRIGGER aos_record_insert AFTER INSERT ON external_records BEGIN
 INSERT INTO aos_search(record_id,title,text) VALUES(new.record_id,new.title,new.text);
END;
CREATE TRIGGER aos_record_update AFTER UPDATE OF title,text ON external_records BEGIN
 DELETE FROM aos_search WHERE record_id=old.record_id;
 INSERT INTO aos_search(record_id,title,text) VALUES(new.record_id,new.title,new.text);
END;
CREATE TRIGGER aos_record_delete AFTER DELETE ON external_records BEGIN
 DELETE FROM aos_search WHERE record_id=old.record_id;
END;
-- Shared evidence projection: reports remain owned by the original dashboard.
CREATE TRIGGER aos_report_insert AFTER INSERT ON reports BEGIN
 INSERT OR REPLACE INTO external_records(record_id,event_id,source_id,external_record_id,original_url,title,text,language,kind,category,published_at,observed_at,ingested_at,updated_at,country,latitude,longitude,precision,confidence,metadata)
 VALUES(new.report_id,new.event_id,new.source_id,new.external_id,new.source_url,new.title,new.description,new.language,new.sentiment_kind,
 json_extract(new.metadata,'$.category'),new.published_at,new.occurred_at,new.ingested_at,new.updated_at,
 json_extract(new.metadata,'$.country_code'),json_extract(new.metadata,'$.latitude'),json_extract(new.metadata,'$.longitude'),
 json_extract(new.metadata,'$.location_precision'),json_extract(new.metadata,'$.confidence'),new.metadata);
END;
CREATE TRIGGER aos_report_update AFTER UPDATE ON reports BEGIN
 UPDATE external_records SET title=new.title,text=new.description,language=new.language,kind=new.sentiment_kind,
 published_at=new.published_at,observed_at=new.occurred_at,updated_at=new.updated_at,indexed_at=CASE WHEN old.title!=new.title OR old.description!=new.description OR old.language!=new.language OR old.metadata!=new.metadata THEN NULL ELSE indexed_at END,
 country=json_extract(new.metadata,'$.country_code'),latitude=json_extract(new.metadata,'$.latitude'),
 longitude=json_extract(new.metadata,'$.longitude'),precision=json_extract(new.metadata,'$.location_precision'),
 confidence=json_extract(new.metadata,'$.confidence'),metadata=new.metadata WHERE record_id=new.report_id;
END;
CREATE TRIGGER aos_report_delete AFTER DELETE ON reports BEGIN
 DELETE FROM external_records WHERE record_id=old.report_id;
END;
INSERT INTO external_records(record_id,event_id,source_id,external_record_id,original_url,title,text,language,kind,category,published_at,observed_at,ingested_at,updated_at,country,latitude,longitude,precision,confidence,metadata)
 SELECT report_id,event_id,source_id,external_id,source_url,title,description,language,sentiment_kind,
 json_extract(metadata,'$.category'),published_at,occurred_at,ingested_at,updated_at,
 json_extract(metadata,'$.country_code'),json_extract(metadata,'$.latitude'),json_extract(metadata,'$.longitude'),
 json_extract(metadata,'$.location_precision'),json_extract(metadata,'$.confidence'),metadata FROM reports;
CREATE TABLE entities(entity_id TEXT PRIMARY KEY,type TEXT NOT NULL,name TEXT NOT NULL,normalized_name TEXT NOT NULL,ambiguity TEXT NOT NULL DEFAULT 'unresolved',created_at TEXT NOT NULL);
CREATE INDEX aos_entities_name ON entities(normalized_name,type);
CREATE TABLE entity_aliases(entity_id TEXT NOT NULL REFERENCES entities(entity_id),alias TEXT NOT NULL,PRIMARY KEY(entity_id,alias));
CREATE TABLE entity_source_mentions(entity_id TEXT NOT NULL REFERENCES entities(entity_id),record_id TEXT NOT NULL REFERENCES external_records(record_id) ON DELETE CASCADE,PRIMARY KEY(entity_id,record_id));
CREATE TABLE relationships(relationship_id TEXT PRIMARY KEY,from_id TEXT NOT NULL REFERENCES entities(entity_id),to_id TEXT NOT NULL REFERENCES entities(entity_id),type TEXT NOT NULL,status TEXT NOT NULL,valid_from TEXT,valid_to TEXT,basis TEXT NOT NULL);
CREATE INDEX aos_edges_from ON relationships(from_id);
CREATE INDEX aos_edges_to ON relationships(to_id);
CREATE TABLE relationship_evidence(relationship_id TEXT NOT NULL REFERENCES relationships(relationship_id) ON DELETE CASCADE,record_id TEXT NOT NULL REFERENCES external_records(record_id) ON DELETE CASCADE,PRIMARY KEY(relationship_id,record_id));
CREATE TABLE cyber_indicators(indicator_id TEXT PRIMARY KEY,type TEXT NOT NULL,value TEXT NOT NULL,normalized_value TEXT NOT NULL,first_seen_at TEXT,last_seen_at TEXT,UNIQUE(type,normalized_value));
CREATE TABLE indicator_evidence(indicator_id TEXT NOT NULL REFERENCES cyber_indicators(indicator_id),record_id TEXT NOT NULL REFERENCES external_records(record_id) ON DELETE CASCADE,classification TEXT NOT NULL,confidence TEXT NOT NULL,PRIMARY KEY(indicator_id,record_id));
CREATE TABLE narrative_clusters(cluster_id TEXT PRIMARY KEY,title TEXT NOT NULL,language TEXT NOT NULL,method TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE narrative_members(cluster_id TEXT NOT NULL REFERENCES narrative_clusters(cluster_id),record_id TEXT PRIMARY KEY REFERENCES external_records(record_id) ON DELETE CASCADE,sentiment TEXT NOT NULL,score REAL,confidence TEXT NOT NULL);
CREATE TABLE narrative_metrics(cluster_id TEXT NOT NULL REFERENCES narrative_clusters(cluster_id),day TEXT NOT NULL,language TEXT NOT NULL,count INTEGER NOT NULL,PRIMARY KEY(cluster_id,day,language));
CREATE TABLE saved_narrative_searches(id TEXT PRIMARY KEY,name TEXT NOT NULL,query TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE media_evidence(id TEXT PRIMARY KEY,filename TEXT NOT NULL,mime TEXT NOT NULL,bytes INTEGER NOT NULL,sha256 TEXT,original_url TEXT,uploaded_at TEXT NOT NULL,metadata TEXT NOT NULL,deleted_at TEXT);
CREATE TABLE media_verifications(id TEXT PRIMARY KEY,media_id TEXT NOT NULL REFERENCES media_evidence(id),step TEXT NOT NULL,result TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE geographic_evidence(id TEXT PRIMARY KEY,title TEXT NOT NULL,geojson TEXT NOT NULL,precision TEXT NOT NULL,basis TEXT NOT NULL,source_url TEXT NOT NULL,acquired_at TEXT,retrieved_at TEXT NOT NULL,license_classification TEXT NOT NULL);
CREATE TABLE watch_sources(id TEXT PRIMARY KEY,url TEXT NOT NULL,title TEXT NOT NULL,interval_seconds INTEGER NOT NULL,enabled INTEGER NOT NULL,permission_basis TEXT NOT NULL,etag TEXT,last_modified TEXT,next_run TEXT,last_success TEXT,error TEXT,failures INTEGER NOT NULL DEFAULT 0);
CREATE TABLE webpage_snapshots(id TEXT PRIMARY KEY,watch_id TEXT NOT NULL REFERENCES watch_sources(id),hash TEXT NOT NULL,text TEXT NOT NULL,retrieved_at TEXT NOT NULL,UNIQUE(watch_id,hash));
CREATE TABLE source_changes(id TEXT PRIMARY KEY,watch_id TEXT NOT NULL REFERENCES watch_sources(id),previous_id TEXT REFERENCES webpage_snapshots(id),current_id TEXT NOT NULL REFERENCES webpage_snapshots(id),diff TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE document_records(id TEXT PRIMARY KEY,title TEXT NOT NULL,organization TEXT NOT NULL,jurisdiction TEXT,source_id TEXT NOT NULL,original_url TEXT NOT NULL,published_at TEXT,retrieved_at TEXT NOT NULL,version TEXT NOT NULL,text TEXT NOT NULL,license_classification TEXT NOT NULL,entity_id TEXT REFERENCES entities(entity_id));
CREATE TABLE correlations(id TEXT PRIMARY KEY,event_ids TEXT NOT NULL,score REAL NOT NULL,method_version TEXT NOT NULL,basis TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE ai_analyses(id TEXT PRIMARY KEY,assessment_type TEXT NOT NULL,response TEXT NOT NULL,model_id TEXT NOT NULL,generated_at TEXT NOT NULL);
CREATE TABLE advanced_ai_usage(id INTEGER PRIMARY KEY,principal TEXT NOT NULL,requested_at TEXT NOT NULL,job_id TEXT NOT NULL);
CREATE TABLE investigation_cases(id TEXT PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL,status TEXT NOT NULL,tags TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,deleted_at TEXT);
CREATE TABLE case_evidence(id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES investigation_cases(id),kind TEXT NOT NULL,reference_id TEXT NOT NULL,snapshot TEXT NOT NULL,sha256 TEXT NOT NULL,added_at TEXT NOT NULL);
CREATE TABLE case_notes(id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES investigation_cases(id),text TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE audit_log(id INTEGER PRIMARY KEY,action TEXT NOT NULL,resource_id TEXT NOT NULL,principal TEXT NOT NULL,created_at TEXT NOT NULL,details TEXT NOT NULL);
CREATE TABLE investigation_jobs(id TEXT PRIMARY KEY,kind TEXT NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL,result TEXT,error TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE INDEX aos_jobs_state ON investigation_jobs(state,created_at);
CREATE TABLE advanced_provider_cache(cache_key TEXT PRIMARY KEY,source_id TEXT NOT NULL,payload TEXT NOT NULL,retrieved_at TEXT NOT NULL,expires_at TEXT NOT NULL);
CREATE TABLE cyber_disruptions(id TEXT PRIMARY KEY,source_id TEXT NOT NULL,country TEXT NOT NULL,name TEXT NOT NULL,start_at TEXT NOT NULL,end_at TEXT NOT NULL,measurement_from TEXT NOT NULL,measurement_until TEXT NOT NULL,method TEXT NOT NULL,datasource TEXT NOT NULL,score REAL,uncertainty REAL,original_url TEXT NOT NULL,retrieved_at TEXT NOT NULL);
CREATE INDEX aos_disruptions_country ON cyber_disruptions(country,start_at DESC);

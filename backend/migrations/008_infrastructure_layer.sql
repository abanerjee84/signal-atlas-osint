-- Keep existing identities, citations, indicators and immutable case snapshots.
UPDATE events SET category='infrastructure' WHERE event_id IN (
 SELECT r.event_id FROM reports r JOIN cyber_observations o ON o.record_id=r.report_id
);
UPDATE reports SET metadata=json_set(metadata,'$.category','infrastructure')
 WHERE report_id IN (SELECT record_id FROM cyber_observations);
UPDATE external_records SET category='infrastructure'
 WHERE record_id IN (SELECT record_id FROM cyber_observations);
UPDATE sources SET category='infrastructure'
 WHERE source_id IN ('dshield','isc_honeypots','threatfox','cloudflare_radar');

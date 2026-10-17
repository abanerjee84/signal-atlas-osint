-- Source commercial-permission register (SRS OSINT-SRS-002, FR-DATA-01).
--
-- Public availability is not permission to redistribute. This table records the
-- separate decision of what a deployment may do with each source's output, so a
-- commercial deployment can refuse a source that a research deployment may keep.
--
-- commercial_use:
--   cleared          - reviewed and permitted for the declared deployment
--   review_required  - not yet reviewed; permitted here, refused in commercial mode
--   blocked          - refused everywhere
--
-- No seed rows assert a licence. Every source without a row is treated as
-- review_required, which is the honest default and keeps existing connectors
-- running until a decision is recorded.
CREATE TABLE IF NOT EXISTS source_permissions (
  source_id TEXT PRIMARY KEY,
  display_class TEXT NOT NULL DEFAULT 'review_required'
    CHECK (display_class IN ('public','attribution','restricted','review_required')),
  commercial_use TEXT NOT NULL DEFAULT 'review_required'
    CHECK (commercial_use IN ('cleared','review_required','blocked')),
  retention_allowed INTEGER NOT NULL DEFAULT 1 CHECK (retention_allowed IN (0,1)),
  export_allowed INTEGER NOT NULL DEFAULT 0 CHECK (export_allowed IN (0,1)),
  derivative_allowed INTEGER NOT NULL DEFAULT 0 CHECK (derivative_allowed IN (0,1)),
  basis TEXT NOT NULL DEFAULT '',
  reviewed_at TEXT,
  reviewer TEXT
);

CREATE INDEX IF NOT EXISTS source_permissions_commercial ON source_permissions(commercial_use);

-- Sources named in docs/WORLDMONITOR_INCORPORATION_PLAN.md section I as needing
-- commercial-use review. These are recorded as internal policy flags, not as
-- statements about the publishers' terms; the reviewer must confirm the basis.
INSERT OR IGNORE INTO source_permissions(source_id,display_class,commercial_use,basis) VALUES
  ('isc_honeypots','restricted','review_required',
   'SANS ISC research feed; commercial-use review required before a paid offering (plan section I)'),
  ('dshield','restricted','review_required',
   'SANS ISC DShield; commercial-use review required before a paid offering (plan section I)'),
  ('sans_diary','attribution','review_required',
   'SANS Internet Storm Center diary; commercial-use review required before a paid offering (plan section I)'),
  ('opensky','attribution','review_required',
   'OpenSky Network; commercial-use review required before a paid offering (plan section I)'),
  ('cna_business','attribution','review_required',
   'CNA RSS terms; commercial-use review required before a paid offering (plan section I)'),
  ('cna_world','attribution','review_required',
   'CNA RSS terms; commercial-use review required before a paid offering (plan section I)'),
  ('cna_asia','attribution','review_required',
   'CNA RSS terms; commercial-use review required before a paid offering (plan section I)');
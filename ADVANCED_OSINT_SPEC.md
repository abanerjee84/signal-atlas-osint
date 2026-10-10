# TECHNICAL SOFTWARE REQUIREMENTS SPECIFICATION

## Advanced OSINT Integration and Investigation Modules

**Document ID:** AOSINT-SRS-001  
**Version:** 1.0  
**Status:** Implementation Specification  
**Date:** 10 October 2026  
**Project Classification:** Open-Source Intelligence, Geospatial Analysis and Digital Investigation  
**Deployment Target:** Ubuntu Linux Server, 8 GB RAM  
**LLM Provider:** OpenRouter (Free Models Preferred)

---

# 1. DOCUMENT PURPOSE AND SCOPE

## 1.1 Purpose

This document specifies the functional, technical, data-processing, integration, security and operational requirements for a collection of advanced OSINT investigation modules.

The system shall support automated ingestion of authorized public intelligence feeds, manual and automated research workflows, entity relationship analysis, media verification, multilingual narrative analysis and cross-domain intelligence correlation.

The modules shall support integration with an existing web-based geospatial intelligence application through documented APIs.

This specification is independently maintained and does not alter any prior software requirements document.

## 1.2 Scope of Implementation

The following modules are included:

| Module ID | Module Name |
|---|---|
| AOS-01 | Unified OSINT Search and Resource Registry |
| AOS-02 | Cyber Threat and Internet Infrastructure Intelligence |
| AOS-03 | Social Media and Narrative Intelligence |
| AOS-04 | Geospatial and Satellite Investigation |
| AOS-05 | Image and Video Verification |
| AOS-06 | Entity Relationship and Network Analysis |
| AOS-07 | Website and Source Change Monitoring |
| AOS-08 | Corporate, Public Records and Document Intelligence |
| AOS-09 | Cross-Domain AI Intelligence Correlation |
| AOS-10 | Investigation Case and Evidence Management |
| AOS-11 | Intelligence Source Validation and Quality Management |

## 1.3 Out of Scope

The implementation shall not include unauthorized access to private accounts, credential harvesting, interception of private communications, intrusive location tracking, bulk profiling of private individuals, scanning of unrelated third-party infrastructure without authorization, or redistribution of restricted third-party datasets.

The system shall not infer precise real-world positions from ambiguous geolocation records or present unsupported AI hypotheses as verified intelligence.

---

# 2. TECHNICAL DESIGN PRINCIPLES

## 2.1 Modular Architecture

Each module shall be independently maintainable.

Modules shall expose functionality through versioned APIs and shall not depend on internal database tables owned by another module without an explicit shared interface.

The system shall follow these principles:

- API-first integration.
- Shared data contracts.
- Source provenance preservation.
- Asynchronous data acquisition.
- Bounded memory consumption.
- Independent connector failure handling.
- Clear distinction between observed, reported and inferred information.
- AI-optional operation.
- Browser-side visualization.
- Server-side credential protection.

## 2.2 Required Technology Compatibility

| Component | Requirement |
|---|---|
| Frontend | HTML, CSS, JavaScript, Vite |
| Backend | Python 3, FastAPI |
| Database | SQLite initially |
| Database mode | Write-Ahead Logging (WAL) |
| HTTP integration | HTTPX asynchronous client |
| Visualization | MapLibre GL JS, ECharts |
| Network visualization | Cytoscape.js or equivalent lightweight library |
| LLM integration | OpenRouter REST API |
| Processing | Python workers with bounded concurrency |
| Deployment | Ubuntu, Nginx, systemd |
| Authentication | Session-based or token-based authentication |
| Transport security | HTTPS for remotely accessible installations |

All components must operate within an 8 GB RAM deployment envelope.

Heavyweight dependencies shall require performance justification before inclusion.

## 2.3 Integration Categories

Every external resource shall be classified as one of the following:

**API Connector:** Official machine-readable API with permitted programmatic access.

**Feed Connector:** RSS, Atom, JSON or comparable published data feed.

**Dataset Importer:** Authorized bulk or periodic structured dataset import.

**Analyst Lookup:** External website opened manually through the investigation interface.

**Local Utility:** A software component executed locally against permitted data.

**Restricted Resource:** Requires credentials, approval, licensing or payment.

**Unavailable Resource:** Inactive, inaccessible or unsuitable for supported integration.

A repository listing or hyperlink shall not be considered evidence of public API availability.

---

# 3. SYSTEM ARCHITECTURE

## 3.1 Logical Components

The system shall implement five architectural layers.

### 3.1.1 Presentation Layer

Provides:

- Unified search interface.
- Investigation workspace.
- OSINT resource directory.
- Cyber intelligence panels.
- Narrative analytics.
- Geospatial investigation.
- Evidence verification.
- Entity relationship visualization.
- AI analysis panel.
- Case management interface.

### 3.1.2 API Layer

Provides:

- Authentication and authorization.
- Query validation.
- Search orchestration.
- Evidence retrieval.
- Cross-module queries.
- Job status reporting.
- AI request control.

### 3.1.3 Intelligence Processing Layer

Provides:

- Source ingestion.
- Normalization.
- Deduplication.
- Entity extraction.
- Text classification.
- Language detection.
- Relationship identification.
- Temporal correlation.
- Source verification.
- Evidence aggregation.

### 3.1.4 Storage Layer

Stores:

- Source metadata.
- Collected public records.
- Normalized events.
- Entities.
- Relationships.
- Media metadata.
- Source snapshots.
- Investigations.
- Evidence references.
- Cached AI analysis.
- Processing and audit logs.

### 3.1.5 External Integration Layer

Connects permitted sources through isolated adapters.

Each adapter shall declare capabilities, authentication requirements, collection frequency, geographic coverage, data format, permissions, and known limitations.

## 3.2 Processing Workflow

The general processing sequence shall be:

1. Discover or register source.
2. Verify access conditions.
3. Retrieve authorized records.
4. Validate response structure.
5. Normalize timestamps and identifiers.
6. Extract geographic references and entities.
7. Deduplicate and associate related records.
8. Store original source references.
9. Calculate relevant aggregates.
10. Invoke AI only when necessary.
11. Publish validated results through the API.
12. Update the investigation interface.

Any stage may reject or quarantine malformed records without stopping unrelated ingestion jobs.

---

# 4. MODULE AOS-01 — UNIFIED OSINT SEARCH AND RESOURCE REGISTRY

## 4.1 Objective

Provide a centralized interface for searching internal intelligence records and discovering appropriate external OSINT research resources.

## 4.2 Functional Requirements

**FR-SEARCH-001:** The system shall provide a universal search field supporting keywords, named entities, countries, geographic locations, domains, IP addresses, organizations and document references.

**FR-SEARCH-002:** Search results shall support the following categories:

- Events
- News and public reporting
- Documents
- Organizations
- Locations
- Domains and IP addresses
- Source resources
- Investigation cases

**FR-SEARCH-003:** Search results shall support filtering by category, date, source, language and relevance.

**FR-SEARCH-004:** Internal search shall use indexed local records without automatically submitting the query to third-party services.

**FR-SEARCH-005:** External research searches shall be initiated only through configured and authorized adapters or explicit user actions.

**FR-SEARCH-006:** The registry shall record whether each resource is free, registration-required, licensed, paid, inactive or unverified.

**FR-SEARCH-007:** Every registry entry shall include its last validation timestamp.

**FR-SEARCH-008:** The system shall support creation of resource-specific search URLs for external manual investigation.

**FR-SEARCH-009:** Unsupported or restricted sources shall not be silently scraped.

**FR-SEARCH-010:** The resource registry shall be searchable and filterable by investigation category.

## 4.3 Initial Resource Candidates

- SearXNG
- OCCRP Aleph
- DocumentCloud
- Internet Archive
- GeoNames
- Certificate Transparency search
- Selected national search engines

Actual API integration shall depend on verified provider interfaces and usage terms.

## 4.4 API Requirements

GET /api/v1/osint/search

GET /api/v1/osint/resources

GET /api/v1/osint/resources/{resource_id}

POST /api/v1/osint/search/external

GET /api/v1/osint/search/jobs/{job_id}

The external search endpoint shall accept only registered provider identifiers and validated search parameters.

## 4.5 Acceptance Criteria

- Internal search returns matching source records with pagination.
- Queries can be restricted to an individual category.
- External search actions display provider identity before invocation.
- Restricted providers cannot be invoked without configuration.
- A failed external provider does not prevent internal search.
- Returned references preserve source attribution.

---

# 5. MODULE AOS-02 — CYBER THREAT AND INTERNET INFRASTRUCTURE INTELLIGENCE

## 5.1 Objective

Collect and analyze publicly available cyber threat intelligence, vulnerability reports, internet disruption indicators and internet infrastructure information.

## 5.2 Initial Source Candidates

- Cloudflare Radar
- AlienVault OTX
- AbuseIPDB
- GreyNoise
- Shadowserver
- BGP.tools
- Censys
- Certificate Transparency records
- Public vulnerability advisories
- Published threat-intelligence feeds

Each source shall be separately evaluated for permitted automated access.

## 5.3 Functional Requirements

**FR-CYBER-001:** Support ingestion of authorized threat-intelligence indicators.

**FR-CYBER-002:** Recognize indicator types including IP addresses, domains, URLs, file hashes and CVE identifiers.

**FR-CYBER-003:** Normalize indicators using their appropriate type and canonical representation.

**FR-CYBER-004:** Support on-demand enrichment of an authorized investigation indicator.

**FR-CYBER-005:** Display associated source reports, detection dates and confidence classifications.

**FR-CYBER-006:** Support country-level internet disruption visualization using appropriately aggregated datasets.

**FR-CYBER-007:** Support investigation of BGP and autonomous system information where provided by authorized data sources.

**FR-CYBER-008:** Support cross-referencing CVE identifiers with official advisories.

**FR-CYBER-009:** Maintain the distinction between malicious infrastructure reports and verified cyber incidents.

**FR-CYBER-010:** Prevent automatic conversion of approximate IP geolocation to a precise incident coordinate.

**FR-CYBER-011:** Provide risk or reputation labels only when the label methodology and source are recorded.

**FR-CYBER-012:** Support filtering by indicator type, provider, country, detection interval and confidence.

## 5.4 Data Requirements

Cyber intelligence records shall include:

- indicator_id
- indicator_type
- indicator_value
- normalized_value
- source_id
- first_seen_at
- last_seen_at
- classification
- confidence
- associated_report_ids
- attribution_status
- ingestion_timestamp

## 5.5 API Requirements

GET /api/v1/cyber/indicators

GET /api/v1/cyber/indicators/{id}

POST /api/v1/cyber/enrich

GET /api/v1/cyber/disruptions

GET /api/v1/cyber/vulnerabilities

GET /api/v1/cyber/infrastructure

## 5.6 Acceptance Criteria

- Authorized indicator enrichment works with a configured provider.
- Repeated indicators are deduplicated.
- Conflicting source classifications remain visible.
- Internet disruption results include measurement period and source.
- No unsupported precise geographic attribution is generated.
- Provider quota exhaustion produces a controlled error.

---

# 6. MODULE AOS-03 — SOCIAL MEDIA AND NARRATIVE INTELLIGENCE

## 6.1 Objective

Analyze accessible public discourse and media narratives to identify topic evolution, sentiment distribution, emerging claims and changes in reported public discussion.

## 6.2 Data Sources

Possible sources include:

- Public Reddit content through permitted APIs.
- Authorized public Telegram channel feeds.
- Public news and RSS sources.
- Public YouTube metadata where permitted.
- Other approved social media APIs.

Private communications and account-restricted information are excluded.

## 6.3 Functional Requirements

**FR-NARR-001:** Ingest permitted public text records and associated metadata.

**FR-NARR-002:** Detect content language.

**FR-NARR-003:** Normalize text for indexing while preserving the original-language content.

**FR-NARR-004:** Extract topic references, named entities and geographic mentions.

**FR-NARR-005:** Group semantically or lexically related records into narrative clusters.

**FR-NARR-006:** Calculate topic-specific sentiment distributions.

**FR-NARR-007:** Track sentiment changes over configurable time intervals.

**FR-NARR-008:** Report record counts, language coverage and contributing sources.

**FR-NARR-009:** Detect changes in narrative volume relative to a historical baseline.

**FR-NARR-010:** Support cross-language comparison where translation or multilingual analysis is available.

**FR-NARR-011:** Identify potentially contradictory claims without automatically declaring either claim false.

**FR-NARR-012:** Display uncertainty and sampling limitations.

**FR-NARR-013:** Support geographic aggregation only where geography can be reasonably established.

**FR-NARR-014:** Support topic-specific dashboards and saved narrative searches.

## 6.4 Analytical Requirements

The sentiment system shall support:

- Positive, negative, neutral and unclassified categories.
- Topic-based sentiment.
- Per-language analysis.
- Time-series aggregation.
- Narrative frequency.
- Coverage distribution.
- Classification confidence.

The system shall not equate online discussion samples with representative national opinion.

## 6.5 Processing Strategy

Use deterministic text processing for initial normalization, language identification, duplicate detection and statistical aggregation.

OpenRouter shall be used for selected narrative summaries, cross-language explanation and contextual analysis.

Routine ingestion shall not depend on a generative LLM.

## 6.6 API Requirements

GET /api/v1/narratives

GET /api/v1/narratives/{id}

GET /api/v1/narratives/trends

GET /api/v1/narratives/sentiment

GET /api/v1/narratives/sources

POST /api/v1/narratives/analyze

## 6.7 Acceptance Criteria

- Narrative clusters retain links to constituent source records.
- Results distinguish topic sentiment from general sentiment.
- Sentiment summaries display sample sizes.
- Geographic visualizations exclude records without defensible geographic attribution.
- Unsupported languages are marked rather than silently misclassified.
- Narrative updates do not require an LLM for every new record.

---

# 7. MODULE AOS-04 — GEOSPATIAL AND SATELLITE INVESTIGATION

## 7.1 Objective

Provide geospatial investigation utilities, coordinate analysis, reference imagery navigation and evidence-based geographic correlation.

## 7.2 Functional Requirements

**FR-GEO-001:** Support coordinate-based search.

**FR-GEO-002:** Support place-name resolution through configured geocoding sources.

**FR-GEO-003:** Display geographic uncertainty for approximate locations.

**FR-GEO-004:** Support distance and area measurements.

**FR-GEO-005:** Support geographic bounding-box searches.

**FR-GEO-006:** Provide external historical imagery investigation links.

**FR-GEO-007:** Support authorized overlay import using GeoJSON.

**FR-GEO-008:** Validate imported coordinate reference systems.

**FR-GEO-009:** Associate geographic evidence with investigation cases.

**FR-GEO-010:** Record imagery acquisition timestamps separately from retrieval timestamps.

**FR-GEO-011:** Support geographic comparison between historical and current reported events.

**FR-GEO-012:** Identify the source and licensing conditions of external imagery.

## 7.3 Geographic Accuracy

Locations shall support these classifications:

- Exact coordinate, independently substantiated.
- Approximate coordinate.
- Administrative region.
- Country only.
- Unresolved.

Coordinates shall not be made artificially precise during normalization.

## 7.4 API Requirements

GET /api/v1/geo/search

GET /api/v1/geo/locations/{id}

POST /api/v1/geo/measure

POST /api/v1/geo/import

GET /api/v1/geo/evidence

## 7.5 Acceptance Criteria

- GeoJSON imports are schema-validated.
- Invalid geographic coordinates are rejected.
- Geographic precision is preserved in API responses.
- Measurement results identify their coordinate and calculation assumptions.
- Historical imagery is not represented as real-time observation.

---

# 8. MODULE AOS-05 — IMAGE AND VIDEO VERIFICATION

## 8.1 Objective

Provide a controlled investigation workspace for examining the metadata, provenance and consistency of authorized public images and video materials.

## 8.2 Resource Candidates

- ExifTool
- Forensically
- Filmot
- Public video metadata tools
- Content Credentials verification utilities
- Authorized reverse-image search services

## 8.3 Functional Requirements

**FR-MEDIA-001:** Accept authorized file uploads or supported public references.

**FR-MEDIA-002:** Validate MIME type, actual file signature and size.

**FR-MEDIA-003:** Extract available metadata from supported file types.

**FR-MEDIA-004:** Compute SHA-256 hashes for uploaded evidence.

**FR-MEDIA-005:** Record original filename, upload time and evidence source.

**FR-MEDIA-006:** Display available timestamps and camera/device metadata without asserting their authenticity.

**FR-MEDIA-007:** Support C2PA credential inspection where technically supported.

**FR-MEDIA-008:** Provide analyst-accessible external verification references.

**FR-MEDIA-009:** Support image comparison where implemented.

**FR-MEDIA-010:** Retain a record of performed verification steps.

**FR-MEDIA-011:** Associate media evidence with a case.

**FR-MEDIA-012:** Allow configurable deletion and retention of uploaded files.

## 8.4 Resource Limits

Initial maximum uploaded file size shall be configurable, with a default of 20 MB.

Video processing shall initially be limited to supported metadata extraction and externally provided references.

CPU-intensive transcoding and bulk video processing are excluded from the initial release.

Media-processing utilities shall have execution timeouts and resource limits.

## 8.5 API Requirements

POST /api/v1/media/evidence

GET /api/v1/media/evidence/{id}

GET /api/v1/media/evidence/{id}/metadata

POST /api/v1/media/evidence/{id}/verify

DELETE /api/v1/media/evidence/{id}

## 8.6 Acceptance Criteria

- Unsupported file formats are rejected.
- Uploaded files cannot execute server-side code.
- Metadata results retain provenance.
- File hashes are reproducible.
- Missing EXIF data is not classified as proof of manipulation.
- Upload cleanup and file retention function correctly.

---

# 9. MODULE AOS-06 — ENTITY RELATIONSHIP AND NETWORK ANALYSIS

## 9.1 Objective

Identify, store and visualize evidence-supported relationships among events, organizations, locations, documents, public institutions and other relevant entities.

## 9.2 Functional Requirements

**FR-GRAPH-001:** Maintain normalized entities with unique internal identifiers.

**FR-GRAPH-002:** Support entity types including country, organization, institution, location, event, document and public infrastructure asset.

**FR-GRAPH-003:** Store typed relationships between entities.

**FR-GRAPH-004:** Associate every relationship with one or more supporting evidence references.

**FR-GRAPH-005:** Store temporal validity where known.

**FR-GRAPH-006:** Distinguish reported relationships from inferred relationships.

**FR-GRAPH-007:** Support interactive graph visualization.

**FR-GRAPH-008:** Support node filtering by type.

**FR-GRAPH-009:** Support relationship filtering by evidence status.

**FR-GRAPH-010:** Support selection of graph nodes to reveal related events and sources.

**FR-GRAPH-011:** Support bounded graph expansion.

**FR-GRAPH-012:** Support entity alias management.

**FR-GRAPH-013:** Preserve ambiguity when multiple entities share the same name.

## 9.3 Storage Requirements

A graph database is not mandatory.

The initial implementation shall use SQLite tables for:

- entities
- entity_aliases
- relationships
- relationship_evidence
- entity_source_mentions

A browser-side graph library shall handle visualization.

## 9.4 API Requirements

GET /api/v1/graph/entities

GET /api/v1/graph/entities/{id}

GET /api/v1/graph/relationships

GET /api/v1/graph/neighborhood/{entity_id}

POST /api/v1/graph/resolve

## 9.5 Acceptance Criteria

- Each displayed relationship has evidence metadata.
- Unverified relationships are visually distinguishable.
- Duplicate entity labels do not cause automatic incorrect merging.
- The API enforces node and edge limits.
- Large graphs use server-side filtering before visualization.

---

# 10. MODULE AOS-07 — WEBSITE AND SOURCE CHANGE MONITORING

## 10.1 Objective

Monitor authorized public webpages and published documents for relevant changes.

## 10.2 Functional Requirements

**FR-WATCH-001:** Allow administrators or authorized analysts to register public monitoring URLs.

**FR-WATCH-002:** Validate URLs against access and security policies.

**FR-WATCH-003:** Support HTTP ETag and Last-Modified conditional requests.

**FR-WATCH-004:** Compute normalized content hashes when appropriate.

**FR-WATCH-005:** Detect meaningful text changes.

**FR-WATCH-006:** Retain bounded historical snapshots.

**FR-WATCH-007:** Show previous and current content differences.

**FR-WATCH-008:** Allow configurable polling schedules.

**FR-WATCH-009:** Respect robots policies and provider restrictions.

**FR-WATCH-010:** Support pause and resume.

**FR-WATCH-011:** Notify the event processing system when relevant changes occur.

**FR-WATCH-012:** Optionally request OpenRouter summaries of significant changes.

## 10.3 Security Requirements

The monitor shall implement SSRF protection.

The system must block access to loopback, link-local, private and otherwise restricted network destinations unless explicitly authorized through a separate trusted administrative mechanism.

DNS resolution and redirect destinations shall both be validated.

Arbitrary URL fetching shall not be exposed as an unrestricted public API.

## 10.4 API Requirements

GET /api/v1/watch/sources

POST /api/v1/watch/sources

PATCH /api/v1/watch/sources/{id}

GET /api/v1/watch/sources/{id}/changes

GET /api/v1/watch/changes/{id}

## 10.5 Acceptance Criteria

- Identical content does not create a change event.
- Meaningful changes generate a versioned record.
- HTTP 304 responses are handled correctly.
- Failed sources use controlled retry/backoff.
- Unauthorized internal-network requests are rejected.
- Monitoring jobs do not overlap indefinitely.

---

# 11. MODULE AOS-08 — CORPORATE, PUBLIC RECORDS AND DOCUMENT INTELLIGENCE

## 11.1 Objective

Support research into publicly documented organizations, institutional relationships, legal records and economic information.

## 11.2 Functional Requirements

**FR-DOC-001:** Provide a searchable directory of supported public-record sources.

**FR-DOC-002:** Index authorized document metadata.

**FR-DOC-003:** Support search by organization, jurisdiction, title, date and source.

**FR-DOC-004:** Store links to original public documents.

**FR-DOC-005:** Support identification of publicly documented organizational relationships.

**FR-DOC-006:** Associate documents with entities and investigation cases.

**FR-DOC-007:** Support optional text extraction for legally obtained documents.

**FR-DOC-008:** Record document version and publication timestamps when known.

**FR-DOC-009:** Support evidence-grounded document summarization.

**FR-DOC-010:** Respect copyright, licensing and redistribution restrictions.

## 11.3 API Requirements

GET /api/v1/documents

GET /api/v1/documents/{id}

GET /api/v1/documents/sources

POST /api/v1/documents/analyze

## 11.4 Acceptance Criteria

- Public document metadata is independently searchable.
- Source URLs and retrieval timestamps are preserved.
- Restricted source content is not redistributed without authorization.
- Summaries identify supporting document passages or references.
- Document processing jobs are resource-bounded.

---

# 12. MODULE AOS-09 — CROSS-DOMAIN AI INTELLIGENCE CORRELATION

## 12.1 Objective

Correlate information from different OSINT domains to identify potentially related developments and provide evidence-grounded analytical assistance.

## 12.2 Supported Inputs

- Geopolitical event records.
- Cyber incidents and disruptions.
- Narrative clusters.
- Geographic events.
- Official source changes.
- Public documents.
- Verified investigation evidence.

## 12.3 Functional Requirements

**FR-AI-001:** Accept normalized event and evidence identifiers.

**FR-AI-002:** Identify temporal overlap between records.

**FR-AI-003:** Identify geographic proximity when coordinates are meaningful.

**FR-AI-004:** Identify shared entities and topics.

**FR-AI-005:** Produce candidate event associations using deterministic rules before generative analysis.

**FR-AI-006:** Support evidence-grounded OpenRouter analysis.

**FR-AI-007:** Return supporting and contradictory source references.

**FR-AI-008:** Separate observed correlations from proposed explanations.

**FR-AI-009:** Mark unsupported hypotheses explicitly.

**FR-AI-010:** Cache repeated analysis requests.

**FR-AI-011:** Record model identifier, request timestamp and analysis version.

**FR-AI-012:** Support configurable daily and per-user request limits.

**FR-AI-013:** Continue providing deterministic correlations when OpenRouter is unavailable.

**FR-AI-014:** Reject structured AI outputs that fail validation.

**FR-AI-015:** Treat retrieved documents and external text as untrusted instructions.

## 12.4 Correlation Strategy

The candidate correlation score may combine:

- Temporal similarity.
- Geographic similarity.
- Shared entities.
- Semantic topic overlap.
- Supporting source count.

Weights shall be configurable and versioned.

The correlation score shall not be presented as the probability of causation without independent calibration.

## 12.5 Structured Output Contract

AI assessments shall use a validated structure containing:

- analysis_id
- assessment_type
- event_ids
- observations
- supporting_evidence_ids
- contradictory_evidence_ids
- hypotheses
- limitations
- model_id
- generated_at

Source identifiers generated by the LLM shall be checked against retrieved evidence before publication.

## 12.6 API Requirements

POST /api/v1/correlation/candidates

GET /api/v1/correlation/events/{id}

POST /api/v1/correlation/analyze

GET /api/v1/correlation/analyses/{id}

GET /api/v1/ai/usage

## 12.7 Acceptance Criteria

- Candidate correlations are returned without LLM access.
- AI failures do not block deterministic analysis.
- Unsupported source identifiers are rejected.
- Contradictory evidence is retained.
- Repeated identical requests can reuse cached results.
- Rate-limit exhaustion is handled without cascading failures.

---

# 13. MODULE AOS-10 — INVESTIGATION CASE AND EVIDENCE MANAGEMENT

## 13.1 Objective

Provide a persistent investigation workspace for organizing research results, events, source references, media records and analyst assessments.

## 13.2 Functional Requirements

**FR-CASE-001:** Create named investigation cases.

**FR-CASE-002:** Associate cases with countries, regions, organizations or topics.

**FR-CASE-003:** Save source records to a case.

**FR-CASE-004:** Save evidence references and file hashes.

**FR-CASE-005:** Attach analyst notes.

**FR-CASE-006:** Display a chronological investigation timeline.

**FR-CASE-007:** Maintain an evidence relationship view.

**FR-CASE-008:** Track case modification history.

**FR-CASE-009:** Export selected nonrestricted records to JSON and a human-readable report format.

**FR-CASE-010:** Support case status changes.

**FR-CASE-011:** Enforce access control for private investigation notes.

**FR-CASE-012:** Support deletion and retention policies.

## 13.3 API Requirements

GET /api/v1/cases

POST /api/v1/cases

GET /api/v1/cases/{id}

PATCH /api/v1/cases/{id}

POST /api/v1/cases/{id}/evidence

POST /api/v1/cases/{id}/notes

GET /api/v1/cases/{id}/timeline

POST /api/v1/cases/{id}/export

## 13.4 Acceptance Criteria

- Case records persist across application restarts.
- Evidence references are immutable or versioned.
- Audit history records case modifications.
- Unauthorized users cannot access restricted cases.
- Exports preserve timestamps and provenance.

---

# 14. MODULE AOS-11 — SOURCE VALIDATION AND QUALITY MANAGEMENT

## 14.1 Objective

Maintain an auditable registry of source reliability, availability, licensing and ingestion health.

## 14.2 Functional Requirements

**FR-SRC-001:** Assign every source a unique identifier.

**FR-SRC-002:** Record source owner and official URL.

**FR-SRC-003:** Classify the supported integration mechanism.

**FR-SRC-004:** Record authentication requirements.

**FR-SRC-005:** Record licensing or usage restrictions.

**FR-SRC-006:** Track successful and failed ingestion attempts.

**FR-SRC-007:** Record source freshness.

**FR-SRC-008:** Identify inactive connectors.

**FR-SRC-009:** Preserve original source references after normalization.

**FR-SRC-010:** Support administrator-level source enablement and disablement.

**FR-SRC-011:** Record provider rate-limit settings where known.

**FR-SRC-012:** Prevent sources with unverified automation permissions from being automatically activated.

## 14.3 API Requirements

GET /api/v1/sources

GET /api/v1/sources/{id}

GET /api/v1/sources/{id}/health

PATCH /api/v1/sources/{id}

GET /api/v1/sources/validation-report

---

# 15. COMMON DATA MODEL

## 15.1 Database Entities

The implementation shall define migrations for at least these logical tables:

| Table | Purpose |
|---|---|
| sources | Source registry |
| source_capabilities | API and access metadata |
| source_health | Connector execution state |
| external_records | Original ingested metadata and content references |
| entities | Normalized entities |
| entity_aliases | Alternate identifiers |
| relationships | Typed entity relationships |
| relationship_evidence | Source support for graph edges |
| cyber_indicators | Cyber intelligence indicators |
| narrative_clusters | Narrative groups |
| narrative_members | Source records within narratives |
| narrative_metrics | Aggregated sentiment and frequency |
| media_evidence | Uploaded media metadata |
| geographic_evidence | Location and imagery references |
| webpage_snapshots | Monitored source versions |
| source_changes | Detected content changes |
| document_records | Public document metadata |
| correlations | Deterministic candidate associations |
| ai_analyses | Validated AI results |
| ai_usage | Request and quota accounting |
| investigation_cases | Case metadata |
| case_evidence | Linked evidence |
| case_notes | Analyst notes |
| audit_log | Security and modification history |

## 15.2 Common Provenance Fields

All externally derived intelligence records shall support:

- source_id
- external_record_id
- original_url
- published_at
- observed_at, where applicable
- ingested_at
- last_verified_at
- source_confidence
- verification_status
- content_hash
- license_classification

Missing timestamps shall remain null rather than being replaced with the current time.

## 15.3 Identifier Conventions

Use UUIDs or another documented collision-resistant identifier scheme for internal entities.

Maintain external provider identifiers separately.

Relationship foreign keys shall refer to internal IDs.

## 15.4 Database Performance

Create indexes for frequently accessed date, country, category, source and entity fields.

Use SQLite FTS5 where appropriate for internal text search.

Use WAL mode with a bounded writer strategy and busy timeout.

Database connections must not be held open while waiting on external LLM or network requests.

---

# 16. CROSS-CUTTING API REQUIREMENTS

## 16.1 Versioning

All public application endpoints shall use the `/api/v1/` prefix.

Breaking API changes require a new version or an explicit migration process.

## 16.2 Response Envelope

Standard responses should include:

- data
- meta
- request_id

Error responses shall include:

- error_code
- message
- request_id

## 16.3 Pagination

Collection endpoints shall use bounded pagination.

Default page size: 50 records.

Maximum page size: 200 records, unless a dedicated aggregate endpoint defines a smaller limit.

## 16.4 Validation

All API inputs shall be validated using typed schemas.

Unsupported filters must return clear validation errors.

## 16.5 Asynchronous Jobs

Long-running operations shall return a job identifier rather than block the HTTP request.

Job states shall include:

- queued
- running
- completed
- failed
- cancelled

The system shall expose job status and failure information.

## 16.6 Authentication

Authenticated operations shall enforce authorization based on the requested resource.

Read-only public feeds may be exposed without authentication only through deliberate deployment configuration.

Administrative connector settings, media uploads, private investigations and AI usage management shall require authentication.

---

# 17. NONFUNCTIONAL REQUIREMENTS

## 17.1 Hardware Constraints

The complete additional module collection shall be deployable on an Ubuntu server containing 8 GB RAM.

No module shall require a dedicated GPU.

Generative LLM inference shall be remote.

## 17.2 Memory Management

The implementation shall use:

- Bounded ingestion queues.
- Limited concurrent HTTP requests.
- Streaming or chunked processing where appropriate.
- Database pagination.
- Bounded in-memory caches.
- File upload limits.
- Worker timeouts.
- Cleanup of temporary files.

A maximum ingestion concurrency of four jobs is an initial configuration target, subject to benchmarking.

## 17.3 Performance Requirements

Under a documented representative test dataset:

| Operation | Acceptance Target |
|---|---|
| Cached internal search | p95 ≤ 500 ms |
| Entity detail retrieval | p95 ≤ 300 ms |
| Bounded graph neighborhood retrieval | p95 ≤ 1 second |
| Narrative aggregate retrieval | p95 ≤ 1 second |
| Case creation | p95 ≤ 500 ms |
| Source registry retrieval | p95 ≤ 300 ms |

External provider latency and OpenRouter generation time shall be measured separately.

These targets must be validated against an explicitly defined dataset size, concurrency level and server environment.

## 17.4 AI Quota Management

Free-model quotas shall be configurable.

Provider limits must not be hard-coded as permanent constants.

Requests shall support timeout, retry, rate-limit handling and circuit-breaking.

The system shall enforce application-side request budgets independent of provider-side limits.

## 17.5 Security Requirements

The implementation shall defend against:

- SQL injection.
- Cross-site scripting.
- Server-side request forgery.
- Arbitrary file execution.
- Path traversal.
- Unauthorized API usage.
- Prompt injection.
- Secret disclosure.
- Unbounded request amplification.
- Unsafe redirects.
- Malicious document parsing.

All secrets shall be stored outside the frontend bundle and source control.

External content shall never be allowed to control executable agent instructions.

## 17.6 Availability

Failure of an external data provider shall not prevent access to previously stored intelligence records.

Failure of OpenRouter shall not prevent manual investigation, source search, evidence review or deterministic correlation.

## 17.7 Auditability

System logs shall record:

- Connector execution results.
- Administrative changes.
- Evidence modifications.
- AI analysis invocations.
- Import failures.
- Authorization failures.

Logs shall avoid storing API secrets, passwords or unnecessary personal data.

## 17.8 Backup and Recovery

SQLite database backup shall use a transactionally safe backup procedure.

Media evidence and source snapshots shall be included in a documented backup plan.

A restoration test shall be performed before production acceptance.

---

# 18. FRONTEND INTERFACE REQUIREMENTS

## 18.1 Required Screens

The advanced OSINT modules shall expose these screens:

1. OSINT Search Hub
2. Cyber Intelligence Center
3. Narrative Intelligence Explorer
4. Geospatial Investigation Workspace
5. Media Verification Workspace
6. Entity Relationship Explorer
7. Website Monitoring Console
8. Document Intelligence Explorer
9. AI Correlation Workspace
10. Investigation Case Manager
11. Source Registry and Health Dashboard

## 18.2 Common Interface Elements

All applicable screens shall support:

- Global navigation.
- Search and filtering.
- Source identification.
- Time-range selection.
- Loading and error states.
- Saved investigation actions.
- Source record inspection.
- Evidence confidence indicators.

## 18.3 Responsive Behavior

The interface shall support desktop browsers as the primary operating environment.

Tablet layouts shall preserve essential viewing and navigation capabilities.

Mobile layouts may simplify graph visualization and large analytical tables.

## 18.4 Accessibility

Interactive controls shall provide keyboard navigation, visible focus indicators and accessible labels.

Charts shall provide textual interpretations or accessible data views.

Confidence classifications must not be indicated by color alone.

---

# 19. IMPLEMENTATION PLAN

## Phase 1 — Search, Sources and Cyber Intelligence

**Scope**

- Resource registry.
- Internal search.
- Provider capability classification.
- Cyber indicator schema.
- Selected authorized cyber connectors.
- Source health monitoring.
- API authentication framework.

**Exit criteria**

- Functional internal search.
- Operational source registry.
- At least two configured and verified source adapters.
- Successful controlled provider-failure tests.
- Verified source attribution.

## Phase 2 — Narrative and Website Monitoring

**Scope**

- Text normalization.
- Language detection.
- Narrative clustering.
- Sentiment aggregation.
- Topic trends.
- Webpage change detection.
- Historical source snapshots.

**Exit criteria**

- Evidence-linked narrative clustering.
- Source-aware sentiment results.
- Working change detection with version history.
- Verified quota and ingestion controls.

## Phase 3 — Geospatial and Media Investigation

**Scope**

- Coordinate utilities.
- Geographic evidence management.
- GeoJSON import.
- Media metadata extraction.
- Media hashing.
- Verification workspace.

**Exit criteria**

- Validated geographic imports.
- Working evidence references.
- Secure upload handling.
- Verified media processing limits.

## Phase 4 — Graph and Document Intelligence

**Scope**

- Entity resolution.
- Typed relationships.
- Graph visualization.
- Public document metadata.
- Search and case association.

**Exit criteria**

- Evidence-linked graph display.
- Entity ambiguity handling.
- Operational document search.
- Bounded graph expansion.

## Phase 5 — AI Correlation and Case Management

**Scope**

- Deterministic correlation engine.
- OpenRouter analysis.
- AI output validation.
- Investigation case management.
- Evidence collection.
- Report export.

**Exit criteria**

- Source-grounded AI assessments.
- Functioning non-AI fallback.
- Case persistence.
- Traceable evidence exports.
- Verified application-side AI quota controls.

## Phase 6 — Production Verification

**Scope**

- Security audit.
- Performance testing.
- Memory profiling.
- Database optimization.
- Backup and restoration.
- Operational documentation.

**Exit criteria**

- Tested application on an 8 GB Ubuntu environment.
- No critical unresolved security findings.
- No demonstrated unbounded memory leaks during soak testing.
- Verified backup restoration.
- Documented source limitations and unavailable integrations.

---

# 20. SYSTEM TESTING REQUIREMENTS

## 20.1 Unit Testing

Mandatory test coverage shall include:

- Source normalization.
- Date handling.
- Geographic validation.
- Indicator parsing.
- Deduplication.
- Entity matching.
- Relationship creation.
- Sentiment aggregation.
- Content-change detection.
- Correlation scoring.
- AI response validation.

## 20.2 Integration Testing

At minimum, test:

- Source adapter to database.
- Database to search API.
- Search API to frontend.
- Event to entity graph.
- Media upload to evidence record.
- Source change to monitoring history.
- Correlation candidate to AI analysis.
- Investigation case to exported report.

## 20.3 Security Testing

Test cases shall include:

- Malformed source URLs.
- SSRF attempts.
- Private-network URL access.
- Oversized uploads.
- Invalid file signatures.
- XSS payloads.
- SQL injection attempts.
- Unauthorized case access.
- Malicious instructions embedded in retrieved content.
- API quota exhaustion.

## 20.4 Resource Testing

The system shall be assessed under:

- Repeated scheduled ingestion.
- Simultaneous search queries.
- Graph visualization requests.
- Active AI analysis.
- External provider failures.
- Database maintenance.
- Temporary network loss.

Measure peak RSS, CPU utilization, disk usage and API latency.

---

# 21. DEFINITION OF DONE

A module shall be considered complete only when:

1. Required functionality has been implemented.
2. Documented API endpoints are available.
3. Database migrations are provided.
4. Input validation is present.
5. Operational error handling is implemented.
6. Automated tests pass.
7. Source attribution is retained.
8. Provider permissions have been reviewed.
9. Resource usage is compatible with the deployment target.
10. The module has been demonstrated against real or explicitly labeled test data.
11. Limitations are recorded.
12. Integration interfaces are documented.

An interface alone does not constitute a completed module.

---

# 22. CODING AGENT EXECUTION CONTRACT

## 22.1 Agent Role

The implementing agent shall act as a senior software engineer specializing in backend integration, OSINT data engineering, web security, geospatial systems and evidence-based analytical software.

## 22.2 Execution Rules

The agent shall implement only the capabilities defined in this document unless explicitly instructed otherwise.

The agent shall not alter unrelated existing application functionality.

Before integration, the agent shall inspect available interfaces and determine the minimum compatible implementation.

The agent shall preserve existing application behaviour and provide backward-compatible API integration where possible.

## 22.3 Third-Party Source Requirements

The agent shall not assume that a listed resource provides a usable API.

For every proposed connector, the agent must document:

- Provider name.
- Official endpoint or access mechanism.
- Authentication.
- Rate limits, if documented.
- Data licensing conditions.
- Supported fields.
- Expected update frequency.
- Error behaviour.
- Last successful integration test.

If an external service requires paid access, the agent shall not purchase or activate it.

Instead, the adapter shall remain disabled until authorized configuration is supplied.

## 22.4 Implementation Discipline

The agent shall:

- Use modular Python packages.
- Define typed API schemas.
- Apply database migrations.
- Use secure configuration management.
- Introduce bounded background jobs.
- Separate UI from ingestion logic.
- Reuse approved dependencies when appropriate.
- Avoid unnecessary persistent services.
- Maintain testable interfaces.
- Provide reproducible deployment instructions.

## 22.5 AI Integration Rules

OpenRouter API keys shall remain server-side.

Free models shall be preferred, but model availability shall be configurable.

The agent shall prevent external source content from overriding system instructions.

AI-generated evidence identifiers must be validated against stored records.

The agent shall not fabricate successful API responses, intelligence data, test results or citations.

## 22.6 Completion Reporting

At the end of each development phase, the agent shall report:

- Implemented modules.
- Implemented endpoints.
- Database changes.
- Verified external integrations.
- Tests executed.
- Test outcomes.
- Resource measurements.
- Known limitations.
- Outstanding access requirements.

The agent shall distinguish verified functionality from incomplete, mocked or untested functionality.

---

# 23. REQUIRED DELIVERABLES

The implementation shall produce:

1. Source code for all implemented modules.
2. Backend API routers and schemas.
3. Source connector framework.
4. Database migrations.
5. Frontend investigation interfaces.
6. OpenRouter integration.
7. Source registry configuration.
8. Unit and integration tests.
9. Security configuration.
10. Environment variable template.
11. Deployment instructions.
12. API reference documentation.
13. Data source licensing and capability register.
14. Operational monitoring instructions.
15. Test report.
16. Known-limitations report.

---

# 24. FINAL ACCEPTANCE CONDITIONS

The advanced OSINT module collection shall be accepted when:

- The modules can be integrated using documented APIs.
- Selected permitted data sources are operational.
- Investigation evidence is traceable.
- Narrative and cyber intelligence records can be searched.
- Geographic evidence retains location uncertainty.
- Relationship graphs use evidence-backed edges.
- Media verification processes operate securely.
- Webpage changes are versioned and inspectable.
- AI correlations provide source references.
- Cases and evidence records persist correctly.
- API credentials are protected.
- The deployment remains within the target resource envelope under the documented acceptance workload.
- No required module depends on fabricated intelligence data.

**END OF DOCUMENT — AOSINT-SRS-001, VERSION 1.0**

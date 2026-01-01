# Requirements: Contact Centre Conversational Insights + AI Coach (GCP / Vertex)

## 1) Background and scope
The business operates:
- **Debt collection** (owned debt + purchased portfolios)
- **Small personal loans** (for customers who can’t borrow from banks)

The contact centre handles **inbound** and **outbound** interactions across voice (and potentially chat). The solution provides post-call analytics and an AI-driven coaching layer.

### In scope (v1)
- Ingest conversation artifacts (initially **text transcripts**, later **audio + transcript**)
- Run **Conversational Insights (CI)** analysis
- Store CI outputs in **BigQuery**
- Generate **AI Coach outputs** per conversation and aggregated per agent/week
- Supervisor/QA review and BI dashboards
- Compliance and privacy controls (PII handling, auditability)

### Out of scope (v1)
- Real-time “Agent Assist” during live calls
- Fully automated account changes (e.g., modifying debt records) without human review
- Full telephony provisioning design (assumed handled by existing CCaaS/telephony layer)

---

## 2) Business requirements (functional)

### BR1 — Conversation ingestion
- The system **shall ingest** conversation artifacts for each interaction:
  - transcript (required for v1)
  - metadata (required)
  - audio (optional; future)
- The system shall support both **inbound** and **outbound** calls.
- The system shall be **idempotent** per `conversation_id` (no duplicate ingestion/processing).
- The system shall handle **out-of-order arrivals** (metadata before transcript, and vice versa).

### BR2 — Required metadata capture
Metadata is produced by existing operational systems (CCaaS/CRM/collections system) and must be stored/available for CI + coaching:

Required fields:
- `conversation_id` (unique)
- `direction` (INBOUND | OUTBOUND)
- `business_line` (COLLECTIONS | LOANS)
- `queue` (e.g., hardship | dispute | standard)
- `agent_id` (required), plus optional `team`, `site`
- `portfolio_id` (for purchased debt) and/or `campaign_id` (for outbound campaigns)
- `call_outcome` if known (promise_to_pay | transferred | unresolved | etc.)
- timestamps: `started_at`, `ended_at`, `duration_sec`

### BR3 — CI analysis
- The system shall submit conversations to **Conversational Insights (CI)** for analysis.
- CI outputs shall include (at minimum, where supported by the input modality):
  - topics/call drivers (intent/theme of the call)
  - sentiment indicators (client sentiment, agent sentiment if available)
  - entity extraction (e.g., money amounts, dates, organizations)
  - transcript stored/exported alongside analysis
- If audio is provided, CI audio-derived metrics (e.g., talk/silence ratios) shall be captured.

### BR4 — Storage and analytics
- The system shall persist:
  - raw transcript + metadata references (“system of record”)
  - CI enrichment outputs
  - coaching outputs
- The system shall store these outputs in **BigQuery** to enable:
  - SQL querying and joins with CRM/outcome tables
  - BI dashboards and drilldowns (e.g., Looker / Looker Studio)
  - downstream automation (e.g., QA case creation)

### BR5 — Per-conversation AI coaching
For each conversation, the system shall generate a “coaching card” that includes:
- short summary (bullets)
- detected driver/outcome tags (payment plan, hardship, dispute, complaint risk, etc.)
- compliance checks (pass/fail) with **evidence snippets** from transcript
- risk flags (e.g., wrong-party contact indicators, hardship/vulnerability cues)
- recommended next actions (structured, machine-usable)
- confidence score and model version

### BR6 — Compliance policy awareness
- The coaching process shall incorporate company compliance rules, including:
  - privacy / non-disclosure to third parties (wrong-party contact)
  - non-harassment / non-coercion expectations
  - hardship/vulnerability handling pathways
  - contact preference restrictions (e.g., “don’t call work number”)
- The system shall support **versioned policy content** that may vary by:
  - business line (collections vs loans)
  - direction (inbound vs outbound)
  - queue (hardship vs standard)
  - effective date (policy version applicable on call date)

### BR7 — Aggregated coaching outputs (per agent per week)
- The system shall generate aggregated outputs (minimum weekly) for supervisors:
  - per agent/week summary
  - driver distribution trends
  - top compliance misses (counts + examples)
  - trends in customer sentiment
  - top recommended actions
- Aggregation shall support filtering by business line, queue, campaign/portfolio, team, site.

### BR8 — Supervisor/QA experience
- Supervisors/QA shall be able to:
  - locate and review conversations in CI UI (where applicable)
  - view coaching cards and drill down to transcript evidence
  - access dashboards for trends/KPIs
- The system shall support BI consumption without manual intervention (BigQuery → dashboards).

---

## 3) Compliance, privacy, and governance requirements

### CR1 — PII handling and redaction
- The system shall minimize exposure of PII:
  - raw transcripts/audio (may contain PII) must be stored in restricted storage with least privilege
  - sanitized transcripts (PII redacted/tokenized) must be generated for CI ingestion (**preferred**)
- The system shall support:
  - pre-redaction pipeline (recommended)
  - CI ingestion redaction configuration (optional additional layer)
- The system shall record which redaction method and version was applied per conversation.

### CR2 — Auditability
- The system shall maintain an audit trail per conversation:
  - ingestion time, source URIs, processing status transitions
  - CI analysis timestamp and schema version
  - coaching generation timestamp, model version, policy version used
- Coaching compliance outputs shall include **evidence snippets** and (where applicable) **policy references**.

### CR3 — Access control and segregation
- The system shall implement role-based access control:
  - restricted access to raw transcripts/audio
  - broader access to sanitized analytics artifacts and aggregates
- The system shall separate dev/test/prod environments (datasets, buckets, service accounts).

### CR4 — Data retention
- The system shall enforce retention policies for:
  - raw artifacts (per org policy)
  - sanitized analytics artifacts
  - coaching outputs
- The system shall support legal hold / investigation workflows where required.

---

## 4) Non-functional requirements (NFR)

### NFR1 — Reliability and idempotency
- Ingestion and processing shall be idempotent:
  - retries must not create duplicates
- The system shall handle out-of-order arrivals and race conditions safely.
- Failed items shall be retriable and tracked with error reasons.

### NFR2 — Scalability and performance
- The system shall support contact-centre operational volumes:
  - batch ingestion (hourly/daily) and near-real-time (minutes) modes
- Coaching generation shall be parallelizable and controllable via concurrency limits.
- Target SLAs (to be defined):
  - CI ingestion → BigQuery availability within **X minutes**
  - Coaching card generated within **Y minutes** after CI export is available

### NFR3 — Observability (monitoring, logging, tracing)
The system shall provide end-to-end visibility with correlation by `conversation_id`:
- Metrics:
  - ingestion rate, failure rate, backlog size
  - CI processing latency
  - coaching latency, request volume, token/cost usage
  - per-stage success rate
- Logging:
  - structured logs at each stage
  - error classification (validation, CI ingest, export, coaching)
- Tracing:
  - distributed trace/correlation IDs across dispatcher → CI call → coach runner

### NFR4 — Security
- Service accounts shall use least-privilege IAM.
- Data shall be encrypted in transit and at rest (default GCP + KMS where required).
- Secrets shall be managed securely (Secret Manager or equivalent).
- Network egress controls shall be applied where required (org policy).

### NFR5 — Maintainability and change management
- Policy content must be versioned and deployable without code changes.
- CI export schema version changes must be tracked and validated.
- The system shall include automated tests:
  - transcript/metadata schema validation tests
  - deterministic compliance rules tests
  - CoachAgent output contract tests (JSON schema)
  - regression suite on a fixed evaluation set

### NFR6 — Cost control
- The system shall support cost governance:
  - batch size limits
  - concurrency limits for coaching
  - token budgets for agent calls
  - ability to disable coaching for low-value call types
- The system shall provide cost observability for major cost drivers:
  - calls processed, CI jobs, agent invocations, token consumption

---

## 5) Assumptions and constraints
- Metadata is sourced from operational systems (CCaaS/CRM), not inferred solely by CI.
- Transcript-only is acceptable for v1; audio is optional/future for talk/silence/overlap metrics.
- PII redaction/sanitization is mandatory before broad analytics exposure; raw data access is restricted.
- Some compliance rules are company-specific and must be treated as versioned policy artifacts.


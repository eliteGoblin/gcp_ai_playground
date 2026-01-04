
# Context

Requirement doc in /home/parallels/devel/gcp_ml_playground/usecases/conversation-coach/requirement.md

HLD doc in /home/parallels/devel/gcp_ml_playground/usecases/conversation-coach/design/HLD.md

Use requirement and HLD as context, only do task in LLD

You generate everything you generated in folder artifacts/

# MVP Task 

## Dev Data generation

Create GCS bucket, and required infra/IAM, using Terraform(everything as IaC), in folder artifacts/terraform, create a meaningful terraform file with name for this. 

### What to do
1) Pick a date folder: `2025-12-28/`
2) For each conversation, generate a UUID folder:
   - `2025-12-28/<UUID>/metadata.json`
   - `2025-12-28/<UUID>/transcription.json`
3) Upload the whole date folder to GCS (same structure).

### Data format
- `metadata.json`: deterministic business context (direction, line, queue, agent, campaign/portfolio, outcome, labels)
- `transcription.json`: realistic multi-turn transcript + timestamps offsets (seconds) + optional agent notes

Note:
* A few data been generated in folder /home/parallels/devel/gcp_ml_playground/usecases/conversation-coach/artifacts/data/dev/, check it, enrich it to correct mistake or make it more like real chat. 
* Keep PII(this is generated fake one, I want to use it to build dev pipeline for now)

### GCS upload plan
- Upload folder `2025-12-28/` to:
  - `gs://<PROJECT>-cc-dev/2025-12-28/...`

## Build initial local cli for MVP 

In local MVP, I want everything locally if can: instead of deploy code as lambda/cloud code, I want to focus on the functions of pipeline: have it implement as Python code, and call GCP cloud API/Vertex. i.e "AI coach workflow" run on my machine to "orchestrate" different parts. (instead of building event driven workflow at MVP steps)

I want you generate a python cli app for me in vertex_demo_cli/ folder

All the python code, inside this: I need function: 

* Support submit data (with data folder) into CI(provision needed CI infra in GCP, everything MUST in IaC, terraform). And also get data outside of CI. 
* Support interact with BigQuery Table

Note: 
* Also need to consider later I want to make this workflow running on GCP, e.g cloud run, etc. I want same code still mostly reusable. 
* For now, simplify things: everything cli upload all data in the local dev data, and send to CI. but when ingest into BigQuery, and when update CI exported data, need UPSERT logic, idempotent. 

### Subtask: provision BigQuery table 

* Consolodate the schema of BigQuery table
* Provision the BigQuery Table required: conversation_registry and CI exports 
* Prod grade consideration of BigQuery, not sure it need schema version/migration like plain SQL. 
* Your python code should considered using best-practice for GCP/Vertex/Data engineering for my scenario. Consider maintainable.

Note:
* I want you also create command that help me get info for human to verify the info in GCP: e.g could be CI exports, data in bigquery, etc.
* This cli can used bymyself to explore each step's data in my demo workflow. 
* So this step focus on makeing keep thing works. After MVP, we will discuss and implement the scaling.
* Python code should have proper unit test coverage, with mocking(unit test not interact with real API)

## Phrase matcher and align latest design schema with implemenation, re-analyze all dev conversation. 

* I want you implement phrase matcher(if not already), based on design on /home/parallels/devel/gcp_ml_playground/usecases/conversation-coach/design/features/phrase_matcher.md 
* My understand is need to 

# Task requirement stop here

IGNORE BELOW TASK and text

Next: doing each section one by one. 

Generate dev test data => ingest into GCS => Trigger job, record data in GCP etc(big query)

# Coach & RAG pipeline

Refer to below design document: 

  | #   | Document            | Path                                   | What You'll Learn                                          |
  |-----|---------------------|----------------------------------------|------------------------------------------------------------|
  | 1   | Implementation Plan | .claude/plans/serene-finding-toucan.md | START HERE - Latest architecture, immutable artifact model |
  | 2   | RAG KB Design       | design/rag_knowledge_base_design.md    | Document lifecycle concepts                                |
  | 3   | Metadata Management | design/metadata_management_design.md   | YAML parsing code (reusable)                               |
  | 4   | RAG Pipeline Design | design/rag_pipeline_design.md          | Vertex AI details, costs                                   |

  Key Architecture Points (Final)

  ┌─────────────────────────────────────────────────────────────────────────────┐
  │   IMMUTABLE ARTIFACT MODEL - SUMMARY                                         │
  ├─────────────────────────────────────────────────────────────────────────────┤
  │                                                                             │
  │   Source of Truth:     Local markdown files (not BQ)                        │
  │   UUID Generation:     Deterministic: hash(file_path + version)             │
  │   Artifact Rule:       Never update, always create new version              │
  │   BQ Purpose:          Mirror of local files (history, audit)               │
  │   GCS Purpose:         Active docs only (for Vertex AI indexing)            │
  │                                                                             │
  │   FLOW:                                                                     │
  │   Local files → cc ingest → BQ (mirror) → GCS (active only) → Vertex AI    │
  │                                                                             │
  └─────────────────────────────────────────────────────────────────────────────┘

## Verify 

* E2e should be working: each steps needs verification(e2e means not only generate code, you need to run and verify each step to make sure implementation working)
    * BQ store the KB: each document/artifact has UUID, with metadata extracted, and raw content, most important: status: active or not 
    * Only active doc uploaded to GCS with uuid as file name, as linkage between BQ and Vertex AI search response. 
    * Vertex AI serach output is expected: with reference data. 
    * Coach app output is expected: with ref to metadata: file name, version, ideally section. 
    * Refresh all the dev conversation, and make sure all is generated with per-conversation coach. 
* Make sure python code is added with proper unit test coverage, and python pipline should pass 
* Coach cli should provide proper cmd for human to get each stage's result, so for me to understand and verify

### Test RAG 

* FInd a few dev test data, check if RAG returned expected result: e.g compliance of ASIC break, internal compliance break. and when reference back to original source,if ASIC doc been referredn, if internal coach playbook been referred, etc. (create dev test data if need)

# Roadmap

## ✅ COMPLETED - Phase 1: Foundation

| Milestone | Status | Description |
|-----------|--------|-------------|
| Dev Data Generation | ✅ Done | 9 realistic test conversations in GCS |
| CI Integration | ✅ Done | CCAI Insights enrichment pipeline |
| BigQuery Schema | ✅ Done | conversation_registry, ci_enrichment, coach_analysis |
| Per-Conversation Coach | ✅ Done | ADK agent with scoring, evidence, coaching points |
| RAG Pipeline (E2E) | ✅ Done | KB docs → BQ → GCS → Vertex AI Search → Coach with citations |

### RAG Pipeline Verified (2026-01-04)
- Topics extracted from CI data + transcript
- Vertex AI Search retrieves relevant KB docs
- BQ metadata enriches with doc_id, version, title
- Coach output includes policy citations (POL-xxx, COACH-xxx, EXT-xxx)
- Retrieval audit log in `kb_retrieval_log`
- 14 KB documents indexed (6 policies, 5 coaching, 4 examples)

---

## 🔲 NEXT - Phase 2: Aggregation & Insights

### Priority 1: Aggregate Coaching Reports
| Task | Description |
|------|-------------|
| Daily Agent Summary | Aggregate coaching for each agent per day |
| Weekly Team Report | Team-level trends, common issues |
| Monthly Business Report | Business line metrics, compliance trends |

**Key Questions:**
- Aggregate by: agent_id, team, business_line, queue
- Time windows: daily, weekly, monthly
- Metrics: avg scores, issue frequency, improvement trends

### Priority 2: Coach Bot (Interactive)
| Task | Description |
|------|-------------|
| Agent Chat Interface | Agent asks "what should I improve?" |
| Supervisor Dashboard | "Show me John's coaching history" |
| Fast History Lookup | Query past coaching by agent_id |

**Architecture Options:**
- ADK agent with BQ tool access
- Streamlit/Gradio UI for quick demo
- Slack/Teams integration (future)

---

## 🔲 Phase 3: Production Readiness

### Priority 3: Monitoring & Observability
| Task | Description |
|------|-------------|
| Pipeline Health | Track ingest/coach success rates |
| Latency Metrics | CI analysis, RAG retrieval, coach generation |
| Cost Tracking | Vertex AI API usage, BQ queries |
| Alert System | Failed jobs, schema drift, quality degradation |

**See:** `design/monitoring_system_design.md`

### Priority 4: Deployment
| Task | Description |
|------|-------------|
| Cloud Run Deployment | ADK runtime on GCP |
| Event-Driven Pipeline | Cloud Functions/Workflows |
| CI/CD | Automated testing + deployment |

**See:** `design/adk_runtime_deployment.md`

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-01-04 | RAG fail-fast by default | Require explicit `allow_fallback=True` for embedded policy |
| 2026-01-04 | GCS uses `.txt` files | Vertex AI Search MIME type compatibility |
| 2026-01-04 | Deterministic UUID | hash(file_path + version) for reproducibility |

# Ref


 Gpt conversation ref:

https://chatgpt.com/g/g-p-6949eef71b988191ad94ce159cbc075f-agentai/c/6949bd3d-82ec-8323-91b8-28fc202bac73

Mermaid Time Sequence:


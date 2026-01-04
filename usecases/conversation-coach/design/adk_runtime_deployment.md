# ADK Agent Runtime & Deployment Guide

> Understanding how ADK agents run, deployment options, and DevOps for the Conversation Coach system.

---

## 1. Key Mental Model: ADK Agent is NOT a Server

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         CRITICAL UNDERSTANDING                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ADK Agent = A FUNCTION, not a running service                             │
│                                                                             │
│   Traditional App:                    ADK Agent:                            │
│   ┌─────────────┐                    ┌─────────────┐                        │
│   │   Server    │ ← always running   │  Function   │ ← runs when called     │
│   │   Process   │                    │  (stateless)│                        │
│   │   (stateful)│                    └─────────────┘                        │
│   └─────────────┘                           │                               │
│                                             ▼                               │
│                                    Input → Gemini API → Output              │
│                                                                             │
│   Deployment Question: Not "where does it run?"                             │
│                        But "what TRIGGERS it to run?"                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Current Implementation Summary

### 2.1 What Happens When You Run `cc-coach coach generate`

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Step-by-step execution flow                                                 │
└─────────────────────────────────────────────────────────────────────────────┘

1. CLI invoked
   $ cc-coach coach generate a1b2c3d4-toxic-agent-test-0001
                    │
                    ▼
2. CoachingOrchestrator created
   ├── Connects to BigQuery
   └── Creates CoachingService (Gemini client)
                    │
                    ▼
3. Fetch data from BQ
   ├── ci_enrichment table → transcript, sentiment, phrase matches
   └── conversation_registry → metadata, labels
                    │
                    ▼
4. Build CoachingInput (Pydantic model)
   ├── Parse transcript into turns
   ├── Extract CI flags
   └── Format as prompt text
                    │
                    ▼
5. Call Gemini API (ONE request)
   ┌─────────────────────────────────────────────────────┐
   │ POST https://us-central1-aiplatform.googleapis.com  │
   │                                                     │
   │ Body:                                               │
   │   model: gemini-2.5-flash                           │
   │   contents: [system_prompt + coaching_input]        │
   │   response_schema: CoachingOutput                   │
   │   temperature: 0.2                                  │
   │                                                     │
   │ Response: JSON matching CoachingOutput schema       │
   └─────────────────────────────────────────────────────┘
                    │
                    ▼
6. Parse response into CoachingOutput (Pydantic)
                    │
                    ▼
7. Store result in BQ (coach_analysis table)
                    │
                    ▼
8. Update registry status → COACHED
                    │
                    ▼
9. Done (process exits)
```

### 2.2 Key Components

| Component | File | Purpose |
|-----------|------|---------|
| `CoachingService` | `agents/conversation_coach.py` | Wraps Gemini API call |
| `CoachingOrchestrator` | `services/coaching.py` | Fetch data, call coach, store results |
| `CoachingInput` | `schemas/coaching_input.py` | Input data structure |
| `CoachingOutput` | `schemas/coaching_output.py` | Output data structure |
| `SYSTEM_PROMPT` | `prompts/coach_system_prompt.py` | Scoring rubric, policy |
| CLI | `cli.py` | User interface |

### 2.3 What is NOT Running

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Common misconceptions vs reality                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│ ❌ "ADK agent is a server listening for requests"                           │
│ ✅ ADK agent is code that makes one API call then exits                     │
│                                                                             │
│ ❌ "ADK agent maintains conversation state"                                 │
│ ✅ Each call is independent; state is in BQ                                 │
│                                                                             │
│ ❌ "ADK agent needs to be deployed to handle traffic"                       │
│ ✅ ADK agent needs a TRIGGER (cron, event, manual)                          │
│                                                                             │
│ ❌ "Scaling means running more agent instances"                             │
│ ✅ Scaling means processing more conversations per batch                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Deployment Options (KISS to Complex)

### 3.1 Comparison Matrix

| Option | Trigger | Latency | Complexity | Cost | Use Case |
|--------|---------|---------|------------|------|----------|
| **CLI (local)** | Manual | N/A | Lowest | $0 infra | Dev/MVP |
| **Cloud Scheduler + Cloud Run Job** | Cron | Minutes | Low | Low | **Recommended for prod** |
| **Pub/Sub + Cloud Run Service** | Event | Seconds | Medium | Medium | Near real-time |
| **Eventarc + Cloud Functions** | GCS event | Seconds | Medium | Low | File-triggered |
| **Vertex AI Agent Engine** | Managed | Seconds | High | Higher | Enterprise/multi-agent |

### 3.2 Option 1: CLI (Current - Dev/MVP)

```
┌─────────────────────────────────────────────────────────────────┐
│ Human runs command manually                                     │
│                                                                 │
│   $ cc-coach coach generate-pending --limit 50                  │
│                                                                 │
│ Pros: Simple, no infrastructure                                 │
│ Cons: Manual, not automated                                     │
│ Use for: Development, testing, demos                            │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Option 2: Cloud Scheduler + Cloud Run Job (Recommended)

```
┌─────────────────────────────────────────────────────────────────┐
│                     RECOMMENDED FOR PRODUCTION                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Cloud Scheduler                                                │
│  (every 5 min)                                                  │
│       │                                                         │
│       ▼                                                         │
│  Cloud Run Job                                                  │
│  ┌─────────────────────────────────────────────┐                │
│  │ Container: cc-coach                          │                │
│  │ Command: cc-coach coach generate-pending     │                │
│  │          --limit 100                         │                │
│  │                                              │                │
│  │ 1. Queries BQ: status = 'ENRICHED'           │                │
│  │ 2. For each conversation:                    │                │
│  │    - Build input                             │                │
│  │    - Call Gemini                             │                │
│  │    - Store result                            │                │
│  │ 3. Exit                                      │                │
│  └─────────────────────────────────────────────┘                │
│                                                                 │
│  Pros:                                                          │
│  - Simple to set up                                             │
│  - No always-on infrastructure                                  │
│  - Pay only when running                                        │
│  - Same code as CLI                                             │
│                                                                 │
│  Cons:                                                          │
│  - Up to 5 min latency                                          │
│  - Fixed batch size                                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Terraform/gcloud setup:**

```bash
# Build and push container
gcloud builds submit --tag gcr.io/$PROJECT/cc-coach

# Create Cloud Run Job
gcloud run jobs create coach-runner \
  --image gcr.io/$PROJECT/cc-coach \
  --command "cc-coach" \
  --args "coach,generate-pending,--limit,100" \
  --region us-central1 \
  --service-account coach-sa@$PROJECT.iam.gserviceaccount.com

# Create scheduler
gcloud scheduler jobs create http coach-scheduler \
  --schedule "*/5 * * * *" \
  --uri "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT/jobs/coach-runner:run" \
  --http-method POST \
  --oauth-service-account-email coach-sa@$PROJECT.iam.gserviceaccount.com
```

### 3.4 Option 3: Pub/Sub + Cloud Run Service (Near Real-Time)

```
┌─────────────────────────────────────────────────────────────────┐
│ Event-driven: Process as soon as conversation is enriched      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  CI Enrichment Complete                                         │
│       │                                                         │
│       ▼                                                         │
│  Pub/Sub Topic: conversation-enriched                           │
│  Message: { "conversation_id": "abc123" }                       │
│       │                                                         │
│       ▼                                                         │
│  Cloud Run Service (push subscription)                          │
│  ┌─────────────────────────────────────────────┐                │
│  │ POST /coach                                  │                │
│  │ Body: { "conversation_id": "abc123" }        │                │
│  │                                              │                │
│  │ 1. Fetch conversation from BQ                │                │
│  │ 2. Call Gemini                               │                │
│  │ 3. Store result                              │                │
│  │ 4. Return 200 OK                             │                │
│  └─────────────────────────────────────────────┘                │
│                                                                 │
│  Pros:                                                          │
│  - Near real-time (seconds)                                     │
│  - Auto-scales with load                                        │
│                                                                 │
│  Cons:                                                          │
│  - More complex setup                                           │
│  - Need to handle retries, dead-letter                          │
│  - Minimum instance if you want fast cold start                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.5 Option 4: Vertex AI Agent Engine (Managed)

```
┌─────────────────────────────────────────────────────────────────┐
│ Fully managed by Google - enterprise option                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Vertex AI Agent Engine                                         │
│  ┌─────────────────────────────────────────────┐                │
│  │ • Upload agent definition                    │                │
│  │ • Google manages hosting, scaling            │                │
│  │ • Built-in session management                │                │
│  │ • Built-in tool execution                    │                │
│  │ • REST API to invoke                         │                │
│  └─────────────────────────────────────────────┘                │
│                                                                 │
│  Pros:                                                          │
│  - Zero infrastructure management                               │
│  - Built-in multi-agent orchestration                           │
│  - Integrated with Vertex AI ecosystem                          │
│                                                                 │
│  Cons:                                                          │
│  - Higher cost                                                  │
│  - Less control                                                 │
│  - Overkill for batch processing                                │
│                                                                 │
│  Best for: Interactive agents, chat, complex tool use           │
│  NOT best for: Batch analysis (our use case)                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Multi-Agent Architecture

### 4.1 All Agents Follow Same Pattern

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  Per-Conversation Coach          Daily Summary            Weekly Report     │
│  ┌─────────────────────┐        ┌─────────────────────┐  ┌───────────────┐  │
│  │ Trigger: Every 5min │        │ Trigger: Daily 6am  │  │ Trigger: Mon  │  │
│  │ Input: 1 transcript │        │ Input: Day's scores │  │ Input: Week   │  │
│  │ Output: Coaching    │        │ Output: Agent       │  │ Output: Full  │  │
│  │         scores      │        │         summaries   │  │         report│  │
│  └─────────────────────┘        └─────────────────────┘  └───────────────┘  │
│           │                              │                       │          │
│           └──────────────────────────────┼───────────────────────┘          │
│                                          │                                  │
│                                          ▼                                  │
│                              Same deployment model:                         │
│                              Cloud Scheduler + Cloud Run Job                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Unified Job Structure

```yaml
# All agents as Cloud Run Jobs, different schedules

jobs:
  coach-per-conversation:
    schedule: "*/5 * * * *"  # Every 5 minutes
    command: cc-coach coach generate-pending --limit 100

  coach-daily-summary:
    schedule: "0 6 * * *"    # Daily at 6 AM
    command: cc-coach summary daily --date yesterday

  coach-weekly-report:
    schedule: "0 7 * * MON"  # Monday at 7 AM
    command: cc-coach summary weekly --week last

  coach-monthly-report:
    schedule: "0 8 1 * *"    # 1st of month at 8 AM
    command: cc-coach summary monthly --month last
```

---

## 5. DevOps Considerations

### 5.1 Container Image Versioning

```
┌─────────────────────────────────────────────────────────────────┐
│ Image tagging strategy                                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  gcr.io/project/cc-coach:v1.2.3    ← Semantic version           │
│  gcr.io/project/cc-coach:latest    ← Latest build               │
│  gcr.io/project/cc-coach:sha-abc123 ← Git commit                │
│                                                                 │
│  In Cloud Run Job:                                              │
│  - Dev: Use :latest                                             │
│  - Prod: Use specific :v1.2.3                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Prompt Version Tracking (Already Implemented)

```sql
-- Every coaching result tracks versions
SELECT
  conversation_id,
  model_version,      -- 'gemini-2.5-flash'
  prompt_version,     -- '1.0.0'
  analyzed_at
FROM coach_analysis
WHERE prompt_version = '1.0.0'

-- Compare results across prompt versions
SELECT
  prompt_version,
  AVG(overall_score) as avg_score,
  COUNT(*) as count
FROM coach_analysis
GROUP BY prompt_version
```

### 5.3 Monitoring

```
┌─────────────────────────────────────────────────────────────────┐
│ Key metrics to track                                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Cloud Logging:                                                 │
│  - Job execution logs                                           │
│  - Error messages                                               │
│  - Processing time per conversation                             │
│                                                                 │
│  Cloud Monitoring:                                              │
│  - Job success/failure rate                                     │
│  - Execution duration                                           │
│  - Conversations processed per run                              │
│                                                                 │
│  BigQuery (custom):                                             │
│  - Coaching backlog (status = ENRICHED)                         │
│  - Processing latency (enriched_at to analyzed_at)              │
│  - Score distributions                                          │
│                                                                 │
│  Alerts:                                                        │
│  - Job failure                                                  │
│  - Backlog > threshold                                          │
│  - Latency > threshold                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.4 Cost Tracking

```sql
-- Add token tracking to coach_analysis table (future)
-- For now, estimate based on conversation length

SELECT
  DATE(analyzed_at) as date,
  COUNT(*) as conversations,
  AVG(turn_count) as avg_turns,
  -- Estimate: ~100 tokens/turn input + ~1500 output
  SUM(turn_count * 100 + 1500) / 1000000 * 0.30 as estimated_input_cost,
  COUNT(*) * 1500 / 1000000 * 2.50 as estimated_output_cost
FROM coach_analysis
GROUP BY DATE(analyzed_at)
```

---

## 6. Recommended Production Setup (KISS)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          RECOMMENDED ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│                         Cloud Scheduler                                     │
│                    ┌──────────┬──────────┬──────────┐                       │
│                    │  */5 *   │  0 6 *   │  0 7 MON │                       │
│                    │  (5 min) │  (daily) │ (weekly) │                       │
│                    └────┬─────┴────┬─────┴────┬─────┘                       │
│                         │          │          │                             │
│                         ▼          ▼          ▼                             │
│                    ┌─────────────────────────────────┐                      │
│                    │        Cloud Run Jobs           │                      │
│                    │  ┌───────┐ ┌───────┐ ┌───────┐  │                      │
│                    │  │ coach │ │ daily │ │weekly │  │                      │
│                    │  │ per-  │ │summary│ │report │  │                      │
│                    │  │ conv  │ │       │ │       │  │                      │
│                    │  └───┬───┘ └───┬───┘ └───┬───┘  │                      │
│                    └─────│─────────│─────────│──────┘                      │
│                          │         │         │                              │
│                          └─────────┼─────────┘                              │
│                                    ▼                                        │
│                    ┌─────────────────────────────────┐                      │
│                    │           Gemini API            │                      │
│                    │        (Vertex AI)              │                      │
│                    └───────────────┬─────────────────┘                      │
│                                    │                                        │
│                                    ▼                                        │
│                    ┌─────────────────────────────────┐                      │
│                    │           BigQuery              │                      │
│                    │  ┌─────────────────────────┐    │                      │
│                    │  │ ci_enrichment           │    │                      │
│                    │  │ coach_analysis          │    │                      │
│                    │  │ daily_agent_summary     │    │                      │
│                    │  │ weekly_agent_report     │    │                      │
│                    │  └─────────────────────────┘    │                      │
│                    └─────────────────────────────────┘                      │
│                                                                             │
│  Total infrastructure:                                                      │
│  - 3 Cloud Scheduler jobs                                                   │
│  - 3 Cloud Run Jobs (same container, different commands)                    │
│  - 1 Service Account                                                        │
│  - BigQuery tables (already exist)                                          │
│                                                                             │
│  Cost estimate (100 conversations/day):                                     │
│  - Cloud Run: ~$5/month                                                     │
│  - Cloud Scheduler: ~$0.30/month                                            │
│  - Gemini API: ~$15/month                                                   │
│  - BigQuery: ~$5/month                                                      │
│  - Total: ~$25/month                                                        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Summary: Mental Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  1. ADK Agent = Stateless function that calls Gemini API                    │
│                                                                             │
│  2. Deployment = Choosing a TRIGGER mechanism                               │
│     - Manual (CLI)                                                          │
│     - Scheduled (Cloud Scheduler)                                           │
│     - Event-driven (Pub/Sub)                                                │
│                                                                             │
│  3. KISS approach: Cloud Scheduler + Cloud Run Job                          │
│     - Same code as CLI                                                      │
│     - Containerize and schedule                                             │
│     - No always-on infrastructure                                           │
│                                                                             │
│  4. All agents (per-conv, daily, weekly) use same pattern                   │
│     - Different schedules                                                   │
│     - Different commands                                                    │
│     - Same container image                                                  │
│                                                                             │
│  5. State lives in BigQuery, not in the agent                               │
│     - Conversation data                                                     │
│     - Coaching results                                                      │
│     - Summaries and reports                                                 │
│     - Prompt/model version tracking                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## References

- `cc_coach/agents/conversation_coach.py` - Agent implementation
- `cc_coach/services/coaching.py` - Orchestration logic
- `design/HLD.md` - High-level architecture
- `design/phase1_adk_conversation_coach.md` - Detailed agent design

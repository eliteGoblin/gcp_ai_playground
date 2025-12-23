# Conversation Coach - AI Agent for Contact Center

## Context

Building an AI-powered coaching system for a debt collection contact center. The system analyzes call transcripts and provides real-time coaching suggestions to agents.

### Interview Preparation

Preparing for AI Engineer interview (Jan 7) with focus on:
- ADK (Agent Development Kit)
- AgentEngine
- Customer Engagement Suite
- Conversational Insights (CI)

### Business Domain

Contact center doing debt collection - making calls to remind/chase customers. Want to use AI to improve agent performance and compliance.

## Requirements

### Data Pipeline

1. **Transcript Ingestion**
   - Generate synthetic transcription data via AI
   - Explore existing contact center datasets
   - Support both event-triggered and scheduled ingestion
   - Idempotency for data processing

2. **PII Handling**
   - DLP sanitization before processing
   - Raw bucket → (DLP job) → Sanitized bucket
   - Alternative: Simple PII masking job

### Coach Agent

Given inputs:
- Transcript
- CI (Conversational Insights) signals
- Company policies

Produce outputs:
- **Suggestions**: Coaching tips linked to specific sentences
- **Actions**: Update contact details, schedule next callback
- **QA Flags**: Automatically mark sessions for quality review

### System Design Pillars

- Security (DLP, IAM, data governance)
- Operations (monitoring, alerting, logging)
- Resilience (fault tolerance, retry logic)
- Scalability (handle peak call volumes)
- Cost (optimize compute, storage)

## Architecture Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CONVERSATION COACH PIPELINE                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│   Call Recording                                                    │
│        │                                                            │
│        ▼                                                            │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐          │
│   │ Transcribe  │────►│ DLP Sanitize│────►│ CI Analysis │          │
│   │ (Speech-to- │     │ (PII Mask)  │     │ (Sentiment, │          │
│   │  Text)      │     │             │     │  Intent)    │          │
│   └─────────────┘     └─────────────┘     └─────────────┘          │
│                                                  │                  │
│                                                  ▼                  │
│                                           ┌─────────────┐          │
│                                           │ Coach Agent │          │
│                                           │ (ADK/Agent  │          │
│                                           │  Engine)    │          │
│                                           └─────────────┘          │
│                                                  │                  │
│                                                  ▼                  │
│                                           ┌─────────────┐          │
│                                           │ Coaching    │          │
│                                           │ Card (JSON) │          │
│                                           └─────────────┘          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Next Steps

1. **Design Phase**
   - Create HLD (High-Level Design)
   - Create LLD (Low-Level Design) per component
   - Design production-realistic dataset

2. **Build Phase**
   - DLP sanitize → CI ingest pipeline skeleton (with fake transcripts)
   - Single CoachAgent using ADK
   - Input: {metadata + transcript + CI signals}
   - Output: Strict JSON "coaching card"

3. **Demo Preparation**
   - Governance + PII handling talking points
   - ADK sample agent walkthrough

## Technical Stack

- **Agent Framework**: Google ADK (Agent Development Kit)
- **Orchestration**: Agent Engine (Vertex AI)
- **Analytics**: Conversational Insights
- **Data Pipeline**: Cloud Functions / Dataflow
- **Storage**: GCS (raw → sanitized buckets)
- **Security**: Cloud DLP, IAM

## Status

- [ ] HLD document
- [ ] LLD documents
- [ ] Sample dataset
- [ ] DLP pipeline skeleton
- [ ] Coach agent prototype

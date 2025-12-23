# Langfuse LLM Observability - Complete Guide

## Overview

Langfuse is an open-source LLM engineering platform for observability, analytics, and evaluation. It uses **OpenTelemetry (OTEL)** as the transport layer with LLM-specific enrichments on top.

**Demo Location:** `/home/parallels/devel/gcp_ml_playground/artifacts/langfuse/`

---

## Core Concepts & Terminology

### Data Model Hierarchy

```
SESSION (Langfuse-specific) ─── Groups multiple traces (e.g., a conversation)
│
├── TRACE 1 (OTEL standard) ─── One trace = One user request
│   ├── trace_id: "abc123"
│   ├── SPAN: embed_query        (OTEL standard)
│   ├── SPAN: vector_search      (OTEL standard)
│   └── GENERATION: llm_call     (Special span for LLM)
│
├── TRACE 2 ─── Second request, SAME session
│   └── trace_id: "def456"
│
└── TRACE 3 ─── Third request, SAME session
    └── trace_id: "ghi789"

SCORES ─── Quality metrics attached to traces
```

### Terminology Reference

| Term | OTEL Standard? | Scope | Description |
|------|----------------|-------|-------------|
| **Trace** | Yes | ONE request | Root unit for a complete request |
| **Span** | Yes | ONE operation | A single step within a trace |
| **Generation** | No (Langfuse) | LLM call | Special span tracking tokens/cost |
| **Session** | No (Langfuse) | Multiple traces | Groups conversation turns |
| **Score** | No (Langfuse) | Quality metric | Numeric evaluation attached to trace |
| **Event** | Yes | Point-in-time | Timestamped occurrence (no duration) |

### Key Distinction: trace_id vs session_id

```python
# User sends 3 messages in a conversation

# Message 1
result1 = query("Who is Einstein?", session_id="conv_123")
# trace_id: "aaa" ← unique to this request

# Message 2
result2 = query("What did he discover?", session_id="conv_123")
# trace_id: "bbb" ← DIFFERENT trace, SAME session

# Message 3
result3 = query("Tell me more", session_id="conv_123")
# trace_id: "ccc" ← DIFFERENT trace, SAME session
```

---

## How Tracing Works

### Protocol: OTEL + Langfuse Enrichment

```
Your Code → @observe → OTEL Spans → Langfuse SDK → OTLP/HTTP → Langfuse Cloud
```

Langfuse SDK v3 is built on OpenTelemetry:
- Uses OTEL for trace/span structure and context propagation
- Adds LLM-specific semantics (tokens, cost, session_id)
- Sends via OTLP (OpenTelemetry Protocol) over HTTP

### What's Standard vs Custom

| Feature | Standard OTEL | Langfuse Custom |
|---------|---------------|-----------------|
| trace_id, span_id | Yes | - |
| Parent-child nesting | Yes | - |
| Timing/latency | Yes | - |
| **session_id** | No | Yes |
| **user_id** | Partial | First-class |
| **Scores** | No | Yes |
| **Token counts** | GenAI SIG | Enhanced |
| **Cost calculation** | No | Yes |

---

## Multi-Span E2E Tracing

### Example: RAG Pipeline with Nested Spans

```python
from langfuse import observe, Langfuse

langfuse = Langfuse()

@observe(name="rag_pipeline")       # ← ROOT TRACE
def rag_pipeline(query: str, session_id: str):
    langfuse.update_current_trace(
        session_id=session_id,
        user_id="user_123",
        tags=["rag", "production"]
    )

    # Each @observe becomes a CHILD SPAN
    embedding = embed_query(query)        # ← SPAN 1: ~100ms
    docs = vector_search(embedding)       # ← SPAN 2: ~20ms
    context = build_context(docs)         # ← SPAN 3: ~1ms
    answer = generate_answer(context)     # ← SPAN 4: ~1500ms (GENERATION)

    return answer

@observe(name="embed_query")
def embed_query(query: str):
    langfuse.update_current_span(
        metadata={"model": "text-embedding-3-small"}
    )
    return embeddings.embed_query(query)

@observe(name="vector_search")
def vector_search(embedding):
    langfuse.update_current_span(
        metadata={"index": "my_index", "top_k": 5}
    )
    return db.query(embedding)

@observe(name="generate_answer")
def generate_answer(context):
    handler = CallbackHandler()  # ← Captures tokens, cost
    return llm.invoke(messages, config={"callbacks": [handler]})
```

### Resulting Trace Structure

```
TRACE: rag_pipeline (Total: 1.62s)
├── SPAN: embed_query ────────── 100ms  (6%)
│   └── metadata: {model: "text-embedding-3-small"}
├── SPAN: vector_search ──────── 20ms   (1%)
│   └── metadata: {top_k: 5, results: 3}
├── SPAN: build_context ──────── 1ms    (0.1%)
└── GENERATION: generate_answer ─ 1500ms (93%)  ← BOTTLENECK
    ├── model: gpt-4o
    ├── input_tokens: 1,234
    ├── output_tokens: 456
    ├── cost: $0.019
    └── [View Prompt] [View Response]
```

---

## Python Code Patterns

### Pattern 1: Automatic Tracing with @observe

```python
from langfuse import observe

@observe(name="my_function")
def my_function(input):
    # Automatically traced:
    # - Start/end time
    # - Input parameters
    # - Return value
    # - Errors
    return result
```

### Pattern 2: Update Trace Metadata

```python
@observe(name="query")
def query(question, session_id):
    langfuse.update_current_trace(
        name="custom_name",
        session_id=session_id,
        user_id="user_123",
        metadata={"key": "value"},
        tags=["tag1", "tag2"]
    )
    trace_id = langfuse.get_current_trace_id()
```

### Pattern 3: LangChain Integration

```python
from langfuse.langchain import CallbackHandler

handler = CallbackHandler()
llm = ChatOpenAI(model="gpt-4o")
response = llm.invoke(messages, config={"callbacks": [handler]})
# Automatically captures: tokens, cost, latency, full I/O
```

### Pattern 4: Add Quality Scores

```python
langfuse.create_score(
    trace_id="abc123",
    name="user_satisfaction",
    value=4.5,
    comment="User feedback"
)
```

---

## AI Ops: What Can You Monitor?

### 1. Latency Breakdown

```
Where is time spent?

TRACE: rag_query (Total: 1.5s)
├── embed_query ──────── 120ms  (8%)
├── vector_search ────── 45ms   (3%)
├── rerank ───────────── 60ms   (4%)
└── llm_generate ─────── 1270ms (85%) ← BOTTLENECK
```

### 2. Cost Tracking

```
Per request, user, day:

GENERATION: llm_generate
├── Model: gpt-4o
├── Input tokens: 1,234
├── Output tokens: 456
├── Cost: $0.0187
└── Daily total: $47.32
```

### 3. Error Analysis

```
Last 24 hours:
├── Total: 10,000 traces
├── Success: 9,750 (97.5%)
├── Errors: 250 (2.5%)
│   ├── TimeoutError: 150 (vector_search)
│   ├── RateLimitError: 80 (llm_generate)
│   └── ValidationError: 20 (build_prompt)
```

### 4. Quality Monitoring

```
Scores distribution:
├── 5 stars: 45%
├── 4 stars: 30%
├── 3 stars: 15%
├── 2 stars: 7%
└── 1 star: 3%

Insight: Low scores correlate with retrieval_score < 0.7
```

---

## Configuration

### Environment Variables

```bash
export LANGFUSE_SECRET_KEY="sk-lf-..."
export LANGFUSE_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_HOST="https://cloud.langfuse.com"
```

### Python Initialization

```python
from langfuse import Langfuse

langfuse = Langfuse()  # Uses env vars
# Or explicitly:
langfuse = Langfuse(
    secret_key="sk-lf-...",
    public_key="pk-lf-...",
    host="https://cloud.langfuse.com"
)
```

---

## Files Reference

```
artifacts/langfuse/
├── requirements.txt           # Dependencies
├── storyteller.py             # Character tone demo
├── test_langfuse_features.py  # Feature demonstration
├── rag_e2e_tracing_demo.py    # Multi-span tracing demo
└── rag_local_demo.py          # Complete RAG with tracing
```

---

## Dashboard Views

| View | What It Shows |
|------|---------------|
| **Traces** | List of all requests with latency, tokens, cost |
| **Trace Detail** | Timeline view with nested spans |
| **Sessions** | Grouped conversations |
| **Analytics** | Cost trends, token usage, latency distribution |
| **Scores** | Quality metrics distribution |

---

## Summary

| Feature | Purpose |
|---------|---------|
| **Traces** | Track complete request execution |
| **Spans** | Track individual operations within trace |
| **Generations** | Track LLM calls with tokens/cost |
| **Sessions** | Group multi-turn conversations |
| **Scores** | Attach quality metrics |
| **Metadata** | Custom filtering attributes |

**View dashboard:** https://cloud.langfuse.com

# Non-Functional Requirements

## Code Quality

- Mypy type checking
- Linting, formatting (ruff/black)

## Scaling Considerations (Post-MVP)

### 1. Async Analysis

**Current**: `operation.result()` blocks ~15s per conversation

**Improved**:
```python
# Return immediately
op_name = operation.operation.name
# Poll later or use Pub/Sub callback
```

### 2. Event-Driven Processing

```
GCS upload → Eventarc → Cloud Run → CI
```

No manual CLI trigger needed.

### 3. Rate Limiting

- CI API: ~600 req/min quota
- Use Cloud Tasks queue with rate control

### 4. Retry

- Exponential backoff on transient failures
- Dead letter queue for persistent failures

## Priority

| Priority | Improvement | Why |
|----------|-------------|-----|
| High | Async analysis | Unblock processing |
| Medium | Event-driven | Auto-process new files |
| Low | Batch/rate limit | Only needed at scale |

## AI Cost monitoring

Per token cost, conversation. 


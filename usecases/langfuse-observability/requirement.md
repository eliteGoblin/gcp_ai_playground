# Langfuse Observability Demo

## Overview

Explore Langfuse for LLM observability, tracing, and prompt management.

## Setup

```bash
# Set environment variables (get from Langfuse dashboard)
export LANGFUSE_SECRET_KEY="sk-lf-xxx"
export LANGFUSE_PUBLIC_KEY="pk-lf-xxx"
export LANGFUSE_BASE_URL="https://cloud.langfuse.com"
export OPENAI_API_KEY="sk-xxx"
```

## App Scenario

**Famous Person's Story Teller**

- Ask questions about famous historical figures
- Bot answers in character (e.g., Professor Snape, Harry Potter style)
- Configurable tone/personality

## Langfuse Features to Explore

1. **Traces** - Request lifecycle, latency breakdown
2. **Cost Tracking** - Token usage, cost per request
3. **Prompt Management** - Version and manage prompts
4. **Evaluations** - Score and analyze outputs
5. **Sessions** - Group related traces

## Goals

- Build Python app with LangChain + GPT-4o
- Integrate Langfuse for observability
- Explore core features via demo app
- Understand tracing, cost tracking, prompt versioning

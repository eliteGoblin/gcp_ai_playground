"""
E2E Multi-Span Tracing Demo - RAG + LLM Pipeline

This demonstrates how Langfuse traces a complete pipeline with multiple spans:
1. User Query → 2. Embedding → 3. Vector Search (RAG) → 4. LLM Generation

Each step is a SPAN within a single TRACE.
"""

import os
import time
import random
from datetime import datetime
from typing import Optional, List

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langfuse import Langfuse, observe
from langfuse.langchain import CallbackHandler

# Configuration
os.environ["LANGFUSE_SECRET_KEY"] = "sk-lf-8af0f1aa-9a5f-45af-96e8-c70b381fefcc"
os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-lf-265642b1-07da-44b6-bde2-5201df7bb77a"
os.environ["LANGFUSE_HOST"] = "https://cloud.langfuse.com"

OPENAI_API_KEY = os.environ.get("GPT_API_KEY") or os.environ.get("OPENAI_API_KEY")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

langfuse = Langfuse()


# =============================================================================
# SIMULATED RAG COMPONENTS (In real app, these would call actual services)
# =============================================================================

@observe(name="embed_query")
def embed_query(query: str) -> List[float]:
    """
    SPAN 1: Convert query to embedding vector

    In production: This would call OpenAI embeddings API or local model
    Latency tracked: Time to generate embedding
    """
    # Simulate embedding API latency (50-150ms typical)
    time.sleep(random.uniform(0.05, 0.15))

    # Simulated embedding vector (1536 dims for ada-002)
    embedding = [random.random() for _ in range(1536)]

    # You can add custom attributes to current span
    langfuse.update_current_span(
        metadata={
            "model": "text-embedding-ada-002",
            "dimensions": 1536,
            "query_length": len(query)
        }
    )

    return embedding


@observe(name="vector_search")
def vector_search(embedding: List[float], top_k: int = 3) -> List[dict]:
    """
    SPAN 2: Search vector database for similar documents

    In production: This would call Pinecone/Weaviate/Qdrant/pgvector
    Latency tracked: Vector DB query time
    """
    # Simulate vector DB latency (20-100ms typical)
    time.sleep(random.uniform(0.02, 0.10))

    # Simulated search results
    results = [
        {
            "id": "doc_001",
            "content": "Albert Einstein developed the theory of relativity...",
            "score": 0.92,
            "metadata": {"source": "physics_encyclopedia"}
        },
        {
            "id": "doc_002",
            "content": "Einstein's famous equation E=mc² revolutionized physics...",
            "score": 0.88,
            "metadata": {"source": "science_history"}
        },
        {
            "id": "doc_003",
            "content": "The Nobel Prize in Physics 1921 was awarded to Einstein...",
            "score": 0.85,
            "metadata": {"source": "nobel_archive"}
        }
    ]

    # Track retrieval metadata
    langfuse.update_current_span(
        metadata={
            "vector_db": "pinecone",
            "index": "knowledge_base",
            "top_k": top_k,
            "results_count": len(results),
            "top_score": results[0]["score"] if results else 0
        }
    )

    return results[:top_k]


@observe(name="rerank_documents")
def rerank_documents(query: str, documents: List[dict]) -> List[dict]:
    """
    SPAN 3: Re-rank retrieved documents for relevance

    In production: This would call Cohere Rerank or cross-encoder model
    Latency tracked: Reranking time
    """
    # Simulate reranking latency (30-80ms)
    time.sleep(random.uniform(0.03, 0.08))

    # Simulate reranking (in reality, scores would change)
    reranked = sorted(documents, key=lambda x: x["score"], reverse=True)

    langfuse.update_current_span(
        metadata={
            "reranker": "cohere-rerank-v3",
            "input_docs": len(documents),
            "output_docs": len(reranked)
        }
    )

    return reranked


@observe(name="build_prompt")
def build_prompt(query: str, context_docs: List[dict]) -> str:
    """
    SPAN 4: Build the prompt with retrieved context

    Latency tracked: Prompt construction time (usually minimal)
    """
    context = "\n\n".join([doc["content"] for doc in context_docs])

    prompt = f"""Answer the question based on the following context.
If the context doesn't contain relevant information, say so.

Context:
{context}

Question: {query}

Answer:"""

    langfuse.update_current_span(
        metadata={
            "context_docs_count": len(context_docs),
            "prompt_length": len(prompt),
            "context_length": len(context)
        }
    )

    return prompt


@observe(name="llm_generate")
def llm_generate(prompt: str, system_prompt: str = "You are a helpful assistant.") -> str:
    """
    SPAN 5: Generate response with LLM

    This is a GENERATION span (special type of span for LLM calls)
    Tracks: tokens, cost, latency, full prompt/response
    """
    handler = CallbackHandler()
    llm = ChatOpenAI(model="gpt-4o", temperature=0.7, api_key=OPENAI_API_KEY)

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=prompt)
    ]

    response = llm.invoke(messages, config={"callbacks": [handler]})

    return response.content


@observe(name="rag_pipeline")
def rag_pipeline(
    query: str,
    session_id: Optional[str] = None,
    user_id: str = "demo_user"
) -> dict:
    """
    ROOT TRACE: Complete RAG Pipeline

    This is the parent TRACE that contains all child SPANS.
    Each @observe function called inside becomes a nested span.

    Trace Structure:
    ├── rag_pipeline (TRACE - root)
    │   ├── embed_query (SPAN)
    │   ├── vector_search (SPAN)
    │   ├── rerank_documents (SPAN)
    │   ├── build_prompt (SPAN)
    │   └── llm_generate (GENERATION - special span type)
    """
    # Update root trace with metadata
    langfuse.update_current_trace(
        name="rag_query",
        session_id=session_id,
        user_id=user_id,
        metadata={
            "pipeline": "rag_v1",
            "query": query,
            "timestamp": datetime.now().isoformat()
        },
        tags=["rag", "e2e-demo", "production"]
    )

    trace_id = langfuse.get_current_trace_id()

    # Step 1: Embed the query
    embedding = embed_query(query)

    # Step 2: Vector search
    search_results = vector_search(embedding, top_k=3)

    # Step 3: Rerank for better relevance
    reranked_docs = rerank_documents(query, search_results)

    # Step 4: Build prompt with context
    prompt = build_prompt(query, reranked_docs)

    # Step 5: Generate response
    response = llm_generate(prompt)

    return {
        "query": query,
        "response": response,
        "trace_id": trace_id,
        "sources": [doc["metadata"]["source"] for doc in reranked_docs]
    }


# =============================================================================
# DEMONSTRATE PARALLEL SPANS
# =============================================================================

@observe(name="parallel_retrieval")
def parallel_retrieval_demo(query: str) -> dict:
    """
    Demo: Multiple parallel operations in one trace

    In real apps, you might query multiple sources in parallel:
    - Vector DB
    - Knowledge Graph
    - SQL Database
    - External API
    """
    langfuse.update_current_trace(
        name="parallel_retrieval",
        tags=["parallel", "multi-source"]
    )

    trace_id = langfuse.get_current_trace_id()

    # These would be parallel in production (using asyncio/threads)
    # For demo, they're sequential but each is tracked as a separate span

    @observe(name="query_vector_db")
    def query_vector_db():
        time.sleep(0.05)
        return {"source": "vector_db", "results": 3}

    @observe(name="query_knowledge_graph")
    def query_knowledge_graph():
        time.sleep(0.03)
        return {"source": "knowledge_graph", "results": 2}

    @observe(name="query_sql_database")
    def query_sql_database():
        time.sleep(0.02)
        return {"source": "sql", "results": 5}

    results = {
        "vector": query_vector_db(),
        "kg": query_knowledge_graph(),
        "sql": query_sql_database()
    }

    return {"trace_id": trace_id, "results": results}


# =============================================================================
# RUN DEMO
# =============================================================================

def run_e2e_demo():
    """Run the complete E2E tracing demo."""
    print("\n" + "="*70)
    print("E2E RAG PIPELINE TRACING DEMO")
    print("="*70)

    # Demo 1: Single RAG query
    print("\n[Demo 1] Complete RAG Pipeline")
    print("-" * 50)

    result = rag_pipeline(
        query="Tell me about Albert Einstein's contributions to physics",
        session_id="rag_demo_session",
        user_id="demo_user"
    )

    print(f"Query: {result['query']}")
    print(f"Response: {result['response'][:200]}...")
    print(f"Sources: {result['sources']}")
    print(f"Trace ID: {result['trace_id']}")

    # Demo 2: Multi-turn conversation (same session)
    print("\n\n[Demo 2] Multi-turn Conversation (same session)")
    print("-" * 50)

    followup = rag_pipeline(
        query="What was his most famous equation?",
        session_id="rag_demo_session",  # Same session!
        user_id="demo_user"
    )
    print(f"Follow-up Trace ID: {followup['trace_id']}")
    print("Both traces grouped under same session!")

    # Demo 3: Parallel retrieval
    print("\n\n[Demo 3] Parallel Multi-Source Retrieval")
    print("-" * 50)

    parallel_result = parallel_retrieval_demo("Einstein")
    print(f"Parallel Trace ID: {parallel_result['trace_id']}")

    # Flush all traces
    langfuse.flush()

    print("\n" + "="*70)
    print("TRACE STRUCTURE IN LANGFUSE")
    print("="*70)
    print("""
    What you'll see in the Langfuse dashboard:

    TRACE: rag_query
    ├── SPAN: embed_query ────────── 50-150ms
    │   └── metadata: model, dimensions
    ├── SPAN: vector_search ──────── 20-100ms
    │   └── metadata: vector_db, top_k, scores
    ├── SPAN: rerank_documents ───── 30-80ms
    │   └── metadata: reranker model
    ├── SPAN: build_prompt ───────── ~1ms
    │   └── metadata: prompt_length
    └── GENERATION: llm_generate ─── 500-2000ms
        └── tokens, cost, full prompt/response

    Each span shows:
    - Start time / End time
    - Duration (latency)
    - Input/Output
    - Custom metadata
    - Parent-child relationships
    """)

    print("\nView at: https://cloud.langfuse.com")


if __name__ == "__main__":
    run_e2e_demo()

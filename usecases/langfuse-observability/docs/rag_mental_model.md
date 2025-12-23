# RAG (Retrieval-Augmented Generation) - Mental Model

## What is RAG?

RAG = **Give the LLM relevant context before asking it to answer**

Without RAG:
```
User: "What's our company's refund policy?"
LLM: "I don't have information about your specific company..." ❌
```

With RAG:
```
User: "What's our company's refund policy?"
System: [Retrieves policy doc from your database]
LLM: "Based on your policy document, refunds are available within 30 days..." ✓
```

---

## The Mental Model (5 Minutes)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           RAG PIPELINE                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  INDEXING (One-time setup)                                                   │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐           │
│  │   Docs   │ → │  Chunk   │ → │  Embed   │ → │  Vector DB   │           │
│  │ (files)  │    │ (split)  │    │ (→ vec)  │    │   (store)    │           │
│  └──────────┘    └──────────┘    └──────────┘    └──────────────┘           │
│                                                                              │
│  QUERYING (Every request)                                                    │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌────────┐│
│  │  Query   │ → │  Embed   │ → │  Search  │ → │ Context  │ → │  LLM   ││
│  │ (user)   │    │ (→ vec)  │    │ (find)   │    │ (build)  │    │(answer)││
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘    └────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Key Components Explained

### 1. Documents → Your Knowledge Base

```python
# Your corporate docs, PDFs, web pages, database records
documents = [
    {"content": "Our refund policy states...", "source": "policy.pdf"},
    {"content": "Product X specifications...", "source": "products.md"},
]
```

### 2. Chunking → Split into Digestible Pieces

**Why chunk?**
- LLMs have context limits (e.g., 128K tokens)
- Smaller chunks = more precise retrieval
- Typical size: 200-1000 characters

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,      # Characters per chunk
    chunk_overlap=50     # Overlap for context
)

chunks = splitter.split_text(document)
# ["Our refund policy states that...", "Products can be returned...", ...]
```

### 3. Embedding → Convert Text to Vectors

**What's an embedding?**
- A list of numbers (e.g., 1536 floats) representing meaning
- Similar meanings → similar vectors
- "dog" and "puppy" have similar embeddings

```python
from langchain_openai import OpenAIEmbeddings

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

vector = embeddings.embed_query("refund policy")
# [0.023, -0.041, 0.089, ...] (1536 dimensions)
```

### 4. Vector Database → Store & Search

**What it does:**
- Stores embeddings with their text
- Finds similar vectors (semantic search)
- Much smarter than keyword search

**Options:**

| Database | Type | Best For |
|----------|------|----------|
| **ChromaDB** | Local/In-memory | Development, small scale |
| **pgvector** | PostgreSQL ext | Already using Postgres |
| **Pinecone** | Cloud managed | Production, scalable |
| **Weaviate** | Self-hosted | Full control |
| **FAISS** | In-memory | Fast, local |

```python
import chromadb

# Store
collection.add(
    ids=["chunk_1", "chunk_2"],
    embeddings=[vec1, vec2],
    documents=["text1", "text2"]
)

# Search
results = collection.query(
    query_embeddings=[query_vec],
    n_results=3
)
```

### 5. Context Building → Prepare for LLM

```python
def build_context(retrieved_docs):
    context = "\n\n".join([
        f"[Source: {doc['source']}]\n{doc['content']}"
        for doc in retrieved_docs
    ])
    return context

# Result:
# [Source: policy.pdf]
# Our refund policy states that customers can return...
#
# [Source: faq.md]
# Q: How do I get a refund? A: Contact support...
```

### 6. LLM Generation → Answer with Context

```python
prompt = f"""Answer based on this context:

{context}

Question: {user_question}

Answer:"""

response = llm.invoke(prompt)
```

---

## Complete Working Example

```python
"""
Minimal RAG in ~50 lines
"""
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
import chromadb

# 1. SETUP
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
llm = ChatOpenAI(model="gpt-4o")
db = chromadb.Client()
collection = db.create_collection("knowledge")

# 2. INDEX DOCUMENTS (one-time)
documents = [
    "Einstein developed the theory of relativity...",
    "Marie Curie discovered radioactivity...",
]

splitter = RecursiveCharacterTextSplitter(chunk_size=500)
for i, doc in enumerate(documents):
    chunks = splitter.split_text(doc)
    vectors = embeddings.embed_documents(chunks)
    collection.add(
        ids=[f"doc_{i}_chunk_{j}" for j in range(len(chunks))],
        embeddings=vectors,
        documents=chunks
    )

# 3. QUERY (every request)
def ask(question: str) -> str:
    # Embed question
    q_vec = embeddings.embed_query(question)

    # Search
    results = collection.query(query_embeddings=[q_vec], n_results=3)
    context = "\n".join(results["documents"][0])

    # Generate
    prompt = f"Context:\n{context}\n\nQuestion: {question}\nAnswer:"
    return llm.invoke(prompt).content

# Use it
answer = ask("What did Einstein discover?")
```

---

## Tech Stack Decision Tree

```
Do you have existing Postgres?
├── YES → Use pgvector (no new infra)
└── NO
    ├── Development/Prototype?
    │   └── ChromaDB (zero setup)
    └── Production at scale?
        ├── Managed solution? → Pinecone
        └── Self-hosted? → Weaviate/Qdrant
```

---

## Latency Breakdown (Typical)

```
RAG Query: ~1.5-3 seconds total

┌─────────────────────┬────────────┬─────────────────────────────┐
│ Step                │ Latency    │ Notes                       │
├─────────────────────┼────────────┼─────────────────────────────┤
│ Embed query         │ 50-150ms   │ OpenAI API call             │
│ Vector search       │ 10-100ms   │ Local: fast, Cloud: +50ms   │
│ Build context       │ ~1ms       │ String concatenation        │
│ LLM generation      │ 1-3s       │ DOMINANT COST               │
└─────────────────────┴────────────┴─────────────────────────────┘
```

**Key insight:** LLM generation is 80-95% of latency. Optimize by:
- Using faster models (gpt-4o-mini)
- Streaming responses
- Caching frequent queries

---

## Cost Breakdown (Typical)

```
Per 1000 queries with GPT-4o:

┌─────────────────────┬─────────────┬──────────────────┐
│ Component           │ Cost        │ Notes            │
├─────────────────────┼─────────────┼──────────────────┤
│ Query embedding     │ ~$0.02      │ text-embedding-3 │
│ Vector DB           │ ~$0-10      │ Depends on scale │
│ LLM generation      │ ~$25-50     │ DOMINANT COST    │
└─────────────────────┴─────────────┴──────────────────┘
```

---

## Common Patterns

### Pattern 1: Basic RAG
```
Query → Embed → Search → LLM → Answer
```

### Pattern 2: RAG with Reranking
```
Query → Embed → Search (top 10) → Rerank (top 3) → LLM → Answer
```
More accurate, +100ms latency

### Pattern 3: Hybrid Search
```
Query → [Keyword Search + Vector Search] → Merge → LLM → Answer
```
Better for exact matches + semantic

### Pattern 4: RAG with Memory
```
[Conversation History] + Query → Search → LLM → Answer
```
For chatbots with context

---

## Quality Improvement Tips

| Problem | Solution |
|---------|----------|
| Wrong docs retrieved | Improve chunking, add metadata filtering |
| Answer hallucinates | Add "only use provided context" instruction |
| Missing information | Increase top_k, check indexing coverage |
| Slow responses | Use faster model, cache, stream |
| High costs | Use gpt-4o-mini, reduce context size |

---

## Files Reference

```
artifacts/langfuse/
└── rag_local_demo.py    # Complete working RAG with Langfuse tracing
```

### Run the Demo

```bash
cd /home/parallels/devel/gcp_ml_playground/artifacts/langfuse
GPT_API_KEY="your-key" python rag_local_demo.py
```

### What it demonstrates:
1. Document chunking & embedding
2. ChromaDB vector storage
3. Semantic search
4. LLM generation with context
5. Full Langfuse tracing of every step

---

## Summary: RAG in One Sentence

> **RAG retrieves relevant documents from your knowledge base and includes them in the LLM prompt, enabling the model to answer questions about your specific data.**

### Key Tech Needed:
1. **Embedding Model** - Convert text to vectors (OpenAI, Cohere, local)
2. **Vector Database** - Store & search vectors (ChromaDB, pgvector, Pinecone)
3. **LLM** - Generate answers (GPT-4, Claude, Llama)
4. **Chunking Strategy** - Split docs into searchable pieces

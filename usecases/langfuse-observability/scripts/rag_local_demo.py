"""
Local RAG System with Langfuse Tracing

This demonstrates a complete RAG (Retrieval-Augmented Generation) pipeline:
1. Document ingestion → chunking → embedding → store in vector DB
2. Query → embed → retrieve similar docs → generate with LLM

Tech Stack:
- ChromaDB: Local vector database (no external setup needed)
- OpenAI: Embeddings (text-embedding-3-small) + LLM (gpt-4o)
- Langfuse: Full observability tracing

Run: GPT_API_KEY="your-key" python rag_local_demo.py
"""

import os
import hashlib
from typing import List, Optional
from datetime import datetime

# LangChain components
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Vector store
import chromadb
from chromadb.config import Settings

# Langfuse tracing
from langfuse import Langfuse, observe
from langfuse.langchain import CallbackHandler

# =============================================================================
# CONFIGURATION
# =============================================================================

os.environ["LANGFUSE_SECRET_KEY"] = "sk-lf-8af0f1aa-9a5f-45af-96e8-c70b381fefcc"
os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-lf-265642b1-07da-44b6-bde2-5201df7bb77a"
os.environ["LANGFUSE_HOST"] = "https://cloud.langfuse.com"

OPENAI_API_KEY = os.environ.get("GPT_API_KEY") or os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Set GPT_API_KEY or OPENAI_API_KEY")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY

langfuse = Langfuse()

# =============================================================================
# SAMPLE DOCUMENTS (In production: load from files, APIs, databases)
# =============================================================================

SAMPLE_DOCUMENTS = [
    {
        "id": "doc_einstein_1",
        "title": "Albert Einstein - Biography",
        "content": """Albert Einstein (1879-1955) was a German-born theoretical physicist who
developed the theory of relativity, one of the two pillars of modern physics. His work is
known for its influence on the philosophy of science. He is best known to the general public
for his mass–energy equivalence formula E = mc², which has been dubbed "the world's most
famous equation". He received the 1921 Nobel Prize in Physics for his services to theoretical
physics, and especially for his discovery of the law of the photoelectric effect.""",
        "metadata": {"source": "encyclopedia", "topic": "physics", "year": 2024}
    },
    {
        "id": "doc_einstein_2",
        "title": "Einstein's Theory of Relativity",
        "content": """The theory of relativity encompasses two interrelated theories: special
relativity and general relativity. Special relativity applies to all physical phenomena in
the absence of gravity. General relativity explains the law of gravitation and its relation
to other forces of nature. Einstein showed that massive objects cause a distortion in
space-time, which is felt as gravity. The theory predicted phenomena like gravitational waves
and black holes, both later confirmed by observation.""",
        "metadata": {"source": "physics_textbook", "topic": "physics", "year": 2023}
    },
    {
        "id": "doc_einstein_3",
        "title": "Einstein's Nobel Prize",
        "content": """Einstein received the Nobel Prize in Physics in 1921, but not for
relativity. The prize was awarded for his explanation of the photoelectric effect, where
he proposed that light consists of discrete quanta (photons). This work was fundamental
to the development of quantum theory. The Nobel Committee considered relativity too
controversial at the time, though it is now considered his greatest achievement.""",
        "metadata": {"source": "nobel_archive", "topic": "awards", "year": 2024}
    },
    {
        "id": "doc_curie_1",
        "title": "Marie Curie - Biography",
        "content": """Marie Curie (1867-1934) was a Polish-French physicist and chemist who
conducted pioneering research on radioactivity. She was the first woman to win a Nobel Prize,
the first person to win Nobel Prizes in two different sciences (Physics 1903, Chemistry 1911),
and the first woman professor at the University of Paris. She discovered polonium and radium,
and developed mobile radiography units used in World War I.""",
        "metadata": {"source": "encyclopedia", "topic": "physics", "year": 2024}
    },
    {
        "id": "doc_curie_2",
        "title": "Curie's Research on Radioactivity",
        "content": """Marie Curie's research on radioactivity led to the discovery of two
new elements: polonium (named after her native Poland) and radium. She coined the term
"radioactivity" and developed techniques for isolating radioactive isotopes. Her work
laid the foundation for nuclear physics and cancer treatment through radiation therapy.
Tragically, her prolonged exposure to radiation led to her death from aplastic anemia.""",
        "metadata": {"source": "science_history", "topic": "chemistry", "year": 2023}
    },
    {
        "id": "doc_turing_1",
        "title": "Alan Turing - Father of Computer Science",
        "content": """Alan Turing (1912-1954) was a British mathematician and computer scientist.
He formalized concepts of algorithm and computation with the Turing machine, considered a
model of a general-purpose computer. During World War II, he worked at Bletchley Park to
break German ciphers, particularly the Enigma machine. His work saved countless lives and
shortened the war. He also proposed the Turing Test as a measure of machine intelligence.""",
        "metadata": {"source": "encyclopedia", "topic": "computer_science", "year": 2024}
    },
    {
        "id": "doc_turing_2",
        "title": "The Turing Test",
        "content": """The Turing Test, proposed by Alan Turing in 1950, is a test of a machine's
ability to exhibit intelligent behavior equivalent to a human. In the test, a human evaluator
judges natural language conversations between a human and a machine. If the evaluator cannot
reliably distinguish the machine from the human, the machine is said to have passed the test.
Modern AI systems like ChatGPT have sparked debates about whether they truly pass this test.""",
        "metadata": {"source": "ai_research", "topic": "artificial_intelligence", "year": 2024}
    },
]


# =============================================================================
# RAG COMPONENTS WITH LANGFUSE TRACING
# =============================================================================

class LocalRAG:
    """
    Local RAG system with full Langfuse observability.

    Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                     RAG PIPELINE                            │
    ├─────────────────────────────────────────────────────────────┤
    │                                                             │
    │  INDEXING (one-time):                                       │
    │  Documents → Chunking → Embedding → Vector DB               │
    │                                                             │
    │  QUERYING (per request):                                    │
    │  Query → Embedding → Vector Search → Context → LLM → Answer │
    │                                                             │
    └─────────────────────────────────────────────────────────────┘
    """

    def __init__(self, collection_name: str = "knowledge_base"):
        self.collection_name = collection_name

        # Initialize ChromaDB (local, persistent storage)
        self.chroma_client = chromadb.Client(Settings(
            anonymized_telemetry=False,
            is_persistent=False  # In-memory for demo; set True for persistence
        ))

        # Create or get collection
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "RAG knowledge base"}
        )

        # Initialize embeddings model
        self.embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",  # Fast, cheap, good quality
            api_key=OPENAI_API_KEY
        )

        # Text splitter for chunking
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,       # Characters per chunk
            chunk_overlap=50,     # Overlap for context continuity
            separators=["\n\n", "\n", ". ", " ", ""]
        )

    # -------------------------------------------------------------------------
    # INDEXING: Add documents to vector DB
    # -------------------------------------------------------------------------

    @observe(name="index_documents")
    def index_documents(self, documents: List[dict]) -> dict:
        """
        Index documents into the vector database.

        Pipeline: Documents → Chunk → Embed → Store

        This is typically done ONCE when setting up your knowledge base.
        """
        langfuse.update_current_trace(
            name="rag_indexing",
            metadata={"document_count": len(documents)},
            tags=["rag", "indexing"]
        )

        total_chunks = 0

        for doc in documents:
            chunks = self._chunk_document(doc)
            embeddings = self._embed_chunks(chunks)
            self._store_chunks(chunks, embeddings, doc)
            total_chunks += len(chunks)

        return {
            "documents_indexed": len(documents),
            "chunks_created": total_chunks,
            "trace_id": langfuse.get_current_trace_id()
        }

    @observe(name="chunk_document")
    def _chunk_document(self, doc: dict) -> List[str]:
        """
        SPAN: Split document into smaller chunks.

        Why chunk?
        - Embeddings have token limits
        - Smaller chunks = more precise retrieval
        - Typical chunk size: 200-1000 characters
        """
        full_text = f"{doc['title']}\n\n{doc['content']}"
        chunks = self.text_splitter.split_text(full_text)

        langfuse.update_current_span(
            metadata={
                "doc_id": doc["id"],
                "original_length": len(full_text),
                "num_chunks": len(chunks),
                "avg_chunk_size": sum(len(c) for c in chunks) / len(chunks) if chunks else 0
            }
        )

        return chunks

    @observe(name="embed_chunks")
    def _embed_chunks(self, chunks: List[str]) -> List[List[float]]:
        """
        SPAN: Convert text chunks to vector embeddings.

        Embedding model: text-embedding-3-small
        - Dimensions: 1536
        - Cost: ~$0.00002 per 1K tokens
        - Good balance of quality/speed/cost
        """
        embeddings = self.embeddings.embed_documents(chunks)

        langfuse.update_current_span(
            metadata={
                "num_chunks": len(chunks),
                "embedding_model": "text-embedding-3-small",
                "dimensions": len(embeddings[0]) if embeddings else 0
            }
        )

        return embeddings

    @observe(name="store_chunks")
    def _store_chunks(self, chunks: List[str], embeddings: List[List[float]], doc: dict):
        """
        SPAN: Store chunks and embeddings in ChromaDB.
        """
        ids = [f"{doc['id']}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "doc_id": doc["id"],
                "title": doc["title"],
                "chunk_index": i,
                **doc.get("metadata", {})
            }
            for i in range(len(chunks))
        ]

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas
        )

        langfuse.update_current_span(
            metadata={
                "chunks_stored": len(chunks),
                "collection": self.collection_name
            }
        )

    # -------------------------------------------------------------------------
    # QUERYING: Retrieve and generate
    # -------------------------------------------------------------------------

    @observe(name="rag_query")
    def query(
        self,
        question: str,
        top_k: int = 3,
        session_id: Optional[str] = None,
        user_id: str = "demo_user"
    ) -> dict:
        """
        Main RAG query pipeline.

        Pipeline: Query → Embed → Search → Build Context → Generate

        Each step is traced as a separate SPAN in Langfuse.
        """
        langfuse.update_current_trace(
            name="rag_query",
            session_id=session_id,
            user_id=user_id,
            metadata={
                "question": question,
                "top_k": top_k
            },
            tags=["rag", "query", "production"]
        )

        trace_id = langfuse.get_current_trace_id()

        # Step 1: Embed the query
        query_embedding = self._embed_query(question)

        # Step 2: Search vector DB
        retrieved_docs = self._vector_search(query_embedding, top_k)

        # Step 3: Build context from retrieved docs
        context = self._build_context(retrieved_docs)

        # Step 4: Generate answer with LLM
        answer = self._generate_answer(question, context)

        return {
            "question": question,
            "answer": answer,
            "sources": [doc["metadata"]["title"] for doc in retrieved_docs],
            "trace_id": trace_id,
            "session_id": session_id
        }

    @observe(name="embed_query")
    def _embed_query(self, query: str) -> List[float]:
        """
        SPAN: Embed the user's query.

        Latency: ~50-150ms (OpenAI API call)
        """
        embedding = self.embeddings.embed_query(query)

        langfuse.update_current_span(
            metadata={
                "query_length": len(query),
                "embedding_model": "text-embedding-3-small"
            }
        )

        return embedding

    @observe(name="vector_search")
    def _vector_search(self, query_embedding: List[float], top_k: int) -> List[dict]:
        """
        SPAN: Search ChromaDB for similar documents.

        Similarity: Cosine distance (default in ChromaDB)
        Latency: ~5-50ms (local DB)
        """
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )

        # Format results
        docs = []
        for i in range(len(results["ids"][0])):
            docs.append({
                "id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
                "similarity": 1 - results["distances"][0][i]  # Convert distance to similarity
            })

        langfuse.update_current_span(
            metadata={
                "top_k": top_k,
                "results_found": len(docs),
                "top_similarity": docs[0]["similarity"] if docs else 0,
                "avg_similarity": sum(d["similarity"] for d in docs) / len(docs) if docs else 0
            }
        )

        return docs

    @observe(name="build_context")
    def _build_context(self, retrieved_docs: List[dict]) -> str:
        """
        SPAN: Build context string from retrieved documents.

        This formats the retrieved chunks into a prompt-friendly format.
        """
        context_parts = []
        for i, doc in enumerate(retrieved_docs, 1):
            context_parts.append(f"[Source {i}: {doc['metadata'].get('title', 'Unknown')}]\n{doc['content']}")

        context = "\n\n".join(context_parts)

        langfuse.update_current_span(
            metadata={
                "num_sources": len(retrieved_docs),
                "context_length": len(context)
            }
        )

        return context

    @observe(name="generate_answer")
    def _generate_answer(self, question: str, context: str) -> str:
        """
        SPAN (GENERATION): Generate answer using LLM.

        This is the most expensive step:
        - Latency: 500-3000ms
        - Cost: Based on tokens

        The CallbackHandler captures all token/cost details.
        """
        handler = CallbackHandler()
        llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.7,
            api_key=OPENAI_API_KEY
        )

        system_prompt = """You are a helpful assistant that answers questions based on the provided context.
- Use ONLY the information from the context to answer
- If the context doesn't contain the answer, say "I don't have enough information to answer that"
- Cite which source(s) you used in your answer
- Be concise but thorough"""

        user_prompt = f"""Context:
{context}

Question: {question}

Answer:"""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        response = llm.invoke(messages, config={"callbacks": [handler]})

        return response.content


# =============================================================================
# DEMO
# =============================================================================

def run_rag_demo():
    """Run the complete RAG demo with Langfuse tracing."""

    print("\n" + "="*70)
    print("LOCAL RAG SYSTEM WITH LANGFUSE TRACING")
    print("="*70)

    # Initialize RAG system
    rag = LocalRAG(collection_name="scientists_kb")

    # Step 1: Index documents
    print("\n[Step 1] Indexing documents...")
    print("-" * 50)
    index_result = rag.index_documents(SAMPLE_DOCUMENTS)
    print(f"  Indexed: {index_result['documents_indexed']} documents")
    print(f"  Created: {index_result['chunks_created']} chunks")
    print(f"  Trace ID: {index_result['trace_id']}")

    # Step 2: Query the system
    print("\n[Step 2] Querying RAG system...")
    print("-" * 50)

    queries = [
        "What is Einstein famous for?",
        "Who won Nobel Prizes in two different sciences?",
        "What is the Turing Test?",
    ]

    session_id = f"rag_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    for i, query in enumerate(queries, 1):
        print(f"\n  Query {i}: {query}")
        result = rag.query(
            question=query,
            top_k=3,
            session_id=session_id,
            user_id="demo_user"
        )
        print(f"  Answer: {result['answer'][:200]}...")
        print(f"  Sources: {result['sources']}")
        print(f"  Trace ID: {result['trace_id']}")

    # Flush traces
    langfuse.flush()

    print("\n" + "="*70)
    print("WHAT TO SEE IN LANGFUSE DASHBOARD")
    print("="*70)
    print("""
    1. INDEXING TRACE (rag_indexing):
       ├── chunk_document (per doc)
       ├── embed_chunks
       └── store_chunks

    2. QUERY TRACES (rag_query):
       ├── embed_query ────────── ~100ms (embedding API)
       ├── vector_search ──────── ~10ms  (local ChromaDB)
       ├── build_context ──────── ~1ms   (string ops)
       └── generate_answer ────── ~1-2s  (LLM generation)
           └── Shows: tokens, cost, full prompt/response

    3. SESSION VIEW:
       All 3 queries grouped under same session_id

    View at: https://cloud.langfuse.com
    """)


if __name__ == "__main__":
    run_rag_demo()

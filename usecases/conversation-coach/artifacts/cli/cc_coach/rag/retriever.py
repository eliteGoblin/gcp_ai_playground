"""RAG retriever using Vertex AI Search.

Provides retrieval from Vertex AI Search with:
- Query execution against Vertex AI Search data store
- UUID extraction from GCS filenames
- BQ metadata enrichment for citations
- Audit logging of retrievals
"""

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from google.cloud import discoveryengine_v1 as discoveryengine
from rich.console import Console

from cc_coach.rag.config import RAGConfig
from cc_coach.rag.metadata import MetadataStore
from cc_coach.rag.parser import extract_section_from_snippet, parse_frontmatter

console = Console()


def _strip_frontmatter(content: str) -> str:
    """Strip YAML frontmatter from content, returning just the body.

    Args:
        content: Raw content that may include YAML frontmatter

    Returns:
        Content body without frontmatter, or original content if no frontmatter
    """
    try:
        _, body = parse_frontmatter(content)
        return body.strip()
    except ValueError:
        # No frontmatter or invalid format - return as-is
        return content


@dataclass
class RetrievedDocument:
    """A document retrieved from Vertex AI Search with enriched metadata."""

    # From Vertex AI Search
    snippet: str
    relevance_score: float
    gcs_uri: str

    # Extracted/enriched from BQ
    uuid: str = ""
    doc_id: str = ""
    version: str = ""
    title: str = ""
    doc_type: str = ""
    section: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "uuid": self.uuid,
            "doc_id": self.doc_id,
            "version": self.version,
            "title": self.title,
            "doc_type": self.doc_type,
            "section": self.section,
            "snippet": self.snippet,
            "relevance_score": self.relevance_score,
            "gcs_uri": self.gcs_uri,
        }

    def to_citation(self) -> str:
        """Format as a citation string."""
        parts = [self.doc_id]
        if self.version:
            parts.append(f"v{self.version}")
        if self.title:
            parts.append(f"({self.title})")
        if self.section and self.section != "General":
            parts.append(f"Section: {self.section}")
        return " ".join(parts)


@dataclass
class RetrievalResult:
    """Result of a RAG retrieval operation."""

    query: str
    documents: list[RetrievedDocument] = field(default_factory=list)
    retrieval_id: Optional[str] = None

    def to_context(self, max_chars: int = 10000) -> str:
        """Format retrieved documents as context for LLM prompt.

        Args:
            max_chars: Maximum characters for context (to fit in prompt)

        Returns:
            Formatted context string with citations
        """
        if not self.documents:
            return ""

        context_parts = []
        total_chars = 0

        for doc in self.documents:
            citation = f"[{doc.to_citation()}]"
            entry = f"{citation}\n{doc.snippet}\n"

            if total_chars + len(entry) > max_chars:
                break

            context_parts.append(entry)
            total_chars += len(entry)

        return "\n".join(context_parts)


class RAGRetriever:
    """RAG retriever using Vertex AI Search."""

    def __init__(self, config: RAGConfig):
        """Initialize retriever.

        Args:
            config: RAG configuration
        """
        self.config = config
        self.metadata_store = MetadataStore(config)
        self._search_client: Optional[discoveryengine.SearchServiceClient] = None

    @property
    def search_client(self) -> discoveryengine.SearchServiceClient:
        """Lazy-load Vertex AI Search client."""
        if self._search_client is None:
            self._search_client = discoveryengine.SearchServiceClient()
        return self._search_client

    def _extract_uuid_from_uri(self, gcs_uri: str) -> Optional[str]:
        """Extract UUID from GCS URI.

        Expected format: gs://bucket/kb/{uuid}.txt or gs://bucket/kb/{uuid}.md

        Args:
            gcs_uri: Full GCS URI

        Returns:
            UUID string or None if not extractable
        """
        # Match UUID pattern in filename (supports both .txt and .md)
        match = re.search(r"/([a-f0-9-]{36})\.(?:txt|md)$", gcs_uri, re.IGNORECASE)
        if match:
            return match.group(1)

        # Fallback: extract filename without extension
        match = re.search(r"/([^/]+)\.(?:txt|md)$", gcs_uri)
        if match:
            return match.group(1)

        return None

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        conversation_id: Optional[str] = None,
        business_line: Optional[str] = None,
        log_retrieval: bool = True,
    ) -> RetrievalResult:
        """Retrieve relevant documents for a query.

        Args:
            query: Search query
            top_k: Number of results (default: config.default_top_k)
            conversation_id: ID for audit logging
            business_line: Business context filter
            log_retrieval: Whether to log to BQ

        Returns:
            RetrievalResult with retrieved documents
        """
        if top_k is None:
            top_k = self.config.default_top_k

        result = RetrievalResult(query=query)

        # Build search request
        request = discoveryengine.SearchRequest(
            serving_config=self.config.vertex_search_serving_config,
            query=query,
            page_size=top_k,
        )

        # Execute search
        try:
            response = self.search_client.search(request)
        except Exception as e:
            console.print(f"[red]Vertex AI Search error: {e}[/red]")
            return result

        # Process results
        for search_result in response.results:
            doc = search_result.document

            # Extract GCS URI from derived_struct_data.link (preferred) or doc.name
            gcs_uri = ""
            snippet = ""

            if hasattr(doc, "derived_struct_data"):
                struct_data = dict(doc.derived_struct_data)

                # Get GCS URI from link field
                if "link" in struct_data:
                    gcs_uri = struct_data["link"]

                # Get snippet
                if "snippets" in struct_data:
                    snippets = struct_data["snippets"]
                    if snippets:
                        first_snippet = dict(snippets[0]) if snippets else {}
                        snippet = first_snippet.get("snippet", "")
                elif "extractive_answers" in struct_data:
                    answers = struct_data["extractive_answers"]
                    if answers:
                        first_answer = dict(answers[0]) if answers else {}
                        snippet = first_answer.get("content", "")

            # Fallback to doc.name if no link found
            if not gcs_uri and hasattr(doc, "name"):
                gcs_uri = doc.name

            # If no snippet found, try to get from content
            if not snippet and hasattr(doc, "content"):
                content = doc.content
                if hasattr(content, "raw_bytes"):
                    snippet = content.raw_bytes.decode("utf-8")[:500]

            # Get relevance score (may be 0.0 if not provided by API)
            relevance_score = 0.0
            has_relevance_score = False
            if hasattr(search_result, "relevance_score") and search_result.relevance_score:
                relevance_score = search_result.relevance_score
                has_relevance_score = True

            # Extract UUID from GCS URI
            uuid = self._extract_uuid_from_uri(gcs_uri) or ""

            # Create retrieved document
            retrieved_doc = RetrievedDocument(
                snippet=snippet,
                relevance_score=relevance_score,
                gcs_uri=gcs_uri,
                uuid=uuid,
                section=extract_section_from_snippet(snippet),
            )

            # Enrich with BQ metadata if UUID found
            if uuid:
                bq_metadata = self.metadata_store.get_document(uuid)
                if bq_metadata:
                    retrieved_doc.doc_id = bq_metadata.get("doc_id", "")
                    retrieved_doc.version = bq_metadata.get("version", "")
                    retrieved_doc.title = bq_metadata.get("title", "")
                    retrieved_doc.doc_type = bq_metadata.get("doc_type", "")
                    # Use BQ content as snippet if no snippet from search
                    if not snippet:
                        raw_content = bq_metadata.get("raw_content", "")
                        if raw_content:
                            # Strip frontmatter and take first 500 chars as snippet
                            body_content = _strip_frontmatter(raw_content)
                            retrieved_doc.snippet = body_content[:500]
                            retrieved_doc.section = extract_section_from_snippet(
                                retrieved_doc.snippet
                            )

            # Filter by minimum relevance score only if score was provided
            # If no relevance score from API, include result (Vertex AI Search
            # already ranked by relevance)
            if has_relevance_score:
                if relevance_score >= self.config.min_relevance_score:
                    result.documents.append(retrieved_doc)
            else:
                # No relevance score - trust Vertex AI Search ranking
                result.documents.append(retrieved_doc)

        # Log retrieval for audit
        if log_retrieval and conversation_id and result.documents:
            result.retrieval_id = self.metadata_store.log_retrieval(
                conversation_id=conversation_id,
                query_text=query,
                retrieved_docs=[d.to_dict() for d in result.documents],
                business_line=business_line,
            )

        return result

    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> RetrievalResult:
        """Simple search without audit logging.

        Convenience method for testing/exploration.

        Args:
            query: Search query
            top_k: Number of results

        Returns:
            RetrievalResult with retrieved documents
        """
        return self.retrieve(
            query=query,
            top_k=top_k,
            log_retrieval=False,
        )

    def get_context_for_coaching(
        self,
        conversation_topics: list[str],
        conversation_id: str,
        business_line: Optional[str] = None,
        max_context_chars: int = 8000,
    ) -> tuple[str, list[RetrievedDocument]]:
        """Get RAG context for coaching session.

        Combines multiple topic queries into a single context.

        Args:
            conversation_topics: Topics extracted from conversation
            conversation_id: ID for audit logging
            business_line: Business context filter
            max_context_chars: Maximum characters for context

        Returns:
            Tuple of (formatted context string, list of retrieved documents)
        """
        all_docs: list[RetrievedDocument] = []
        seen_uuids: set[str] = set()

        # Query for each topic
        for topic in conversation_topics:
            result = self.retrieve(
                query=topic,
                conversation_id=conversation_id,
                business_line=business_line,
                log_retrieval=True,
            )

            # Add unique documents
            for doc in result.documents:
                if doc.uuid and doc.uuid not in seen_uuids:
                    all_docs.append(doc)
                    seen_uuids.add(doc.uuid)

        # Sort by relevance
        all_docs.sort(key=lambda d: d.relevance_score, reverse=True)

        # Build context with limit
        combined_result = RetrievalResult(
            query=" | ".join(conversation_topics),
            documents=all_docs,
        )

        context = combined_result.to_context(max_chars=max_context_chars)
        return context, all_docs

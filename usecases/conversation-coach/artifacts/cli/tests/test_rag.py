"""Unit tests for RAG module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cc_coach.rag.config import RAGConfig, generate_uuid, VALID_STATUSES, VALID_DOC_TYPES
from cc_coach.rag.parser import (
    parse_frontmatter,
    validate_metadata,
    compute_checksum,
    parse_document,
    extract_section_from_snippet,
    DocumentMetadata,
    ParsedDocument,
)


# =============================================================================
# Config Tests
# =============================================================================

class TestGenerateUUID:
    """Tests for deterministic UUID generation."""

    def test_same_input_produces_same_uuid(self):
        """Same file_path + version should produce same UUID."""
        uuid1 = generate_uuid("documents/policy/POL-001.md", "1.0.0")
        uuid2 = generate_uuid("documents/policy/POL-001.md", "1.0.0")
        assert uuid1 == uuid2

    def test_different_version_produces_different_uuid(self):
        """Different version should produce different UUID."""
        uuid1 = generate_uuid("documents/policy/POL-001.md", "1.0.0")
        uuid2 = generate_uuid("documents/policy/POL-001.md", "1.1.0")
        assert uuid1 != uuid2

    def test_different_path_produces_different_uuid(self):
        """Different file path should produce different UUID."""
        uuid1 = generate_uuid("documents/policy/POL-001.md", "1.0.0")
        uuid2 = generate_uuid("documents/policy/POL-002.md", "1.0.0")
        assert uuid1 != uuid2

    def test_uuid_format(self):
        """UUID should be in standard format."""
        uuid = generate_uuid("test.md", "1.0.0")
        # UUID format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        assert len(uuid) == 36
        assert uuid.count("-") == 4


class TestRAGConfig:
    """Tests for RAGConfig."""

    def test_default_values(self):
        """Config should have sensible defaults."""
        with patch.dict("os.environ", {}, clear=True):
            config = RAGConfig()
            assert config.location == "australia-southeast1"
            assert config.bq_dataset == "conversation_coach"
            assert config.default_top_k == 5

    def test_from_env(self):
        """Config should read from environment."""
        env = {
            "GCP_PROJECT_ID": "test-project",
            "RAG_GCS_BUCKET": "test-bucket",
            "RAG_DATA_STORE_ID": "test-store",
        }
        with patch.dict("os.environ", env, clear=True):
            config = RAGConfig.from_env()
            assert config.project_id == "test-project"
            assert config.gcs_bucket == "test-bucket"
            assert config.data_store_id == "test-store"

    def test_validate_missing_required(self):
        """Validate should report missing required fields."""
        config = RAGConfig(project_id="", gcs_bucket="", data_store_id="")
        errors = config.validate()
        assert len(errors) == 3
        assert any("PROJECT_ID" in e for e in errors)
        assert any("GCS_BUCKET" in e for e in errors)
        assert any("DATA_STORE_ID" in e for e in errors)

    def test_validate_success(self):
        """Validate should pass with all required fields."""
        config = RAGConfig(
            project_id="test",
            gcs_bucket="bucket",
            data_store_id="store",
        )
        errors = config.validate()
        assert len(errors) == 0

    def test_gcs_documents_uri(self):
        """Should construct correct GCS URI."""
        config = RAGConfig(gcs_bucket="my-bucket", gcs_prefix="kb")
        assert config.gcs_documents_uri == "gs://my-bucket/kb"

    def test_bq_full_table_name(self):
        """Should construct correct BQ table name."""
        config = RAGConfig(project_id="proj", bq_dataset="ds")
        assert config.bq_documents_full_table == "proj.ds.kb_documents"


# =============================================================================
# Parser Tests
# =============================================================================

class TestParseFrontmatter:
    """Tests for YAML frontmatter parsing."""

    def test_valid_frontmatter(self):
        """Should parse valid YAML frontmatter."""
        content = """---
doc_id: POL-001
title: Test Policy
version: 1.0.0
status: active
doc_type: policy
---
# Document Content

This is the body.
"""
        metadata, body = parse_frontmatter(content)
        assert metadata["doc_id"] == "POL-001"
        assert metadata["title"] == "Test Policy"
        assert metadata["version"] == "1.0.0"
        assert "# Document Content" in body

    def test_missing_frontmatter(self):
        """Should raise error for missing frontmatter."""
        content = "# Just content without frontmatter"
        with pytest.raises(ValueError, match="YAML frontmatter"):
            parse_frontmatter(content)

    def test_invalid_yaml(self):
        """Should raise error for invalid YAML."""
        content = """---
doc_id: POL-001
  invalid: indentation
---
# Content
"""
        with pytest.raises(ValueError, match="Invalid YAML"):
            parse_frontmatter(content)

    def test_array_fields(self):
        """Should parse array fields correctly."""
        content = """---
doc_id: POL-001
title: Test
version: 1.0.0
status: active
doc_type: policy
business_lines:
  - COLLECTIONS
  - HARDSHIP
---
# Content
"""
        metadata, _ = parse_frontmatter(content)
        assert metadata["business_lines"] == ["COLLECTIONS", "HARDSHIP"]


class TestValidateMetadata:
    """Tests for metadata validation."""

    def test_valid_metadata(self):
        """Should pass for valid metadata."""
        metadata = {
            "doc_id": "POL-001",
            "title": "Test",
            "version": "1.0.0",
            "status": "active",
            "doc_type": "policy",
        }
        errors = validate_metadata(metadata)
        assert len(errors) == 0

    def test_missing_required_fields(self):
        """Should report missing required fields."""
        metadata = {"doc_id": "POL-001"}
        errors = validate_metadata(metadata)
        assert any("Missing required fields" in e for e in errors)

    def test_invalid_status(self):
        """Should reject invalid status."""
        metadata = {
            "doc_id": "POL-001",
            "title": "Test",
            "version": "1.0.0",
            "status": "invalid_status",
            "doc_type": "policy",
        }
        errors = validate_metadata(metadata)
        assert any("Invalid status" in e for e in errors)

    def test_invalid_doc_type(self):
        """Should reject invalid doc_type."""
        metadata = {
            "doc_id": "POL-001",
            "title": "Test",
            "version": "1.0.0",
            "status": "active",
            "doc_type": "invalid_type",
        }
        errors = validate_metadata(metadata)
        assert any("Invalid doc_type" in e for e in errors)

    def test_invalid_version_format(self):
        """Should reject non-semver version."""
        metadata = {
            "doc_id": "POL-001",
            "title": "Test",
            "version": "v1",
            "status": "active",
            "doc_type": "policy",
        }
        errors = validate_metadata(metadata)
        assert any("Invalid version format" in e for e in errors)

    def test_invalid_doc_id_format(self):
        """Should reject non-standard doc_id."""
        metadata = {
            "doc_id": "policy-1",  # Should be POL-001 format
            "title": "Test",
            "version": "1.0.0",
            "status": "active",
            "doc_type": "policy",
        }
        errors = validate_metadata(metadata)
        assert any("Invalid doc_id format" in e for e in errors)

    def test_superseded_requires_superseded_by(self):
        """Superseded status should require superseded_by field."""
        metadata = {
            "doc_id": "POL-001",
            "title": "Test",
            "version": "1.0.0",
            "status": "superseded",
            "doc_type": "policy",
        }
        errors = validate_metadata(metadata)
        assert any("superseded_by is required" in e for e in errors)

    def test_all_valid_statuses(self):
        """All defined statuses should be valid."""
        for status in VALID_STATUSES:
            metadata = {
                "doc_id": "POL-001",
                "title": "Test",
                "version": "1.0.0",
                "status": status,
                "doc_type": "policy",
            }
            if status == "superseded":
                metadata["superseded_by"] = "POL-001:2.0.0"
            errors = validate_metadata(metadata)
            status_errors = [e for e in errors if "Invalid status" in e]
            assert len(status_errors) == 0, f"Status '{status}' should be valid"

    def test_all_valid_doc_types(self):
        """All defined doc_types should be valid."""
        for doc_type in VALID_DOC_TYPES:
            metadata = {
                "doc_id": "POL-001",
                "title": "Test",
                "version": "1.0.0",
                "status": "active",
                "doc_type": doc_type,
            }
            errors = validate_metadata(metadata)
            type_errors = [e for e in errors if "Invalid doc_type" in e]
            assert len(type_errors) == 0, f"Doc type '{doc_type}' should be valid"


class TestComputeChecksum:
    """Tests for checksum computation."""

    def test_same_content_same_checksum(self):
        """Same content should produce same checksum."""
        content = "test content"
        checksum1 = compute_checksum(content)
        checksum2 = compute_checksum(content)
        assert checksum1 == checksum2

    def test_different_content_different_checksum(self):
        """Different content should produce different checksum."""
        checksum1 = compute_checksum("content 1")
        checksum2 = compute_checksum("content 2")
        assert checksum1 != checksum2

    def test_checksum_is_sha256(self):
        """Checksum should be 64 hex characters (SHA-256)."""
        checksum = compute_checksum("test")
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)


class TestParseDocument:
    """Tests for full document parsing."""

    def test_parse_valid_document(self):
        """Should parse a valid markdown document."""
        content = """---
doc_id: POL-001
title: Test Policy
version: 1.0.0
status: active
doc_type: policy
business_lines:
  - COLLECTIONS
---
# Test Policy

This is a test policy document.
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            f.flush()
            file_path = Path(f.name)

        try:
            doc = parse_document(file_path)
            assert isinstance(doc, ParsedDocument)
            assert doc.metadata.doc_id == "POL-001"
            assert doc.metadata.version == "1.0.0"
            assert doc.metadata.status == "active"
            assert doc.metadata.uuid  # Should have generated UUID
            assert doc.metadata.checksum  # Should have checksum
            assert "# Test Policy" in doc.body
            assert doc.raw_content == content
        finally:
            file_path.unlink()

    def test_parse_invalid_document(self):
        """Should raise error for invalid document."""
        content = """---
doc_id: invalid-format
---
# Content
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            f.flush()
            file_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Invalid metadata"):
                parse_document(file_path)
        finally:
            file_path.unlink()

    def test_parse_missing_file(self):
        """Should raise error for missing file."""
        with pytest.raises(FileNotFoundError):
            parse_document(Path("/nonexistent/file.md"))


class TestExtractSectionFromSnippet:
    """Tests for section extraction from snippets."""

    def test_extract_h2_section(self):
        """Should extract ## header."""
        snippet = """## Threats

Agents must never threaten legal action unless..."""
        section = extract_section_from_snippet(snippet)
        assert section == "Threats"

    def test_extract_h3_section(self):
        """Should extract ### header."""
        snippet = """### Subsection

Some content here."""
        section = extract_section_from_snippet(snippet)
        assert section == "Subsection"

    def test_no_section_returns_general(self):
        """Should return 'General' when no header found."""
        snippet = "Just some content without any headers."
        section = extract_section_from_snippet(snippet)
        assert section == "General"

    def test_multiline_snippet(self):
        """Should find section in multiline snippet."""
        snippet = """Some intro text.

## Important Section

Content after the header."""
        section = extract_section_from_snippet(snippet)
        assert section == "Important Section"


# =============================================================================
# Integration Tests (with mocks)
# =============================================================================

class TestDocumentIngester:
    """Tests for DocumentIngester with mocked dependencies."""

    @pytest.fixture
    def mock_config(self):
        """Provide a mock config."""
        return RAGConfig(
            project_id="test-project",
            gcs_bucket="test-bucket",
            data_store_id="test-store",
        )

    def test_scan_documents(self, mock_config):
        """Should find markdown files in directory."""
        from cc_coach.rag.ingest import DocumentIngester

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            Path(tmpdir, "doc1.md").write_text("---\n---\n# Doc 1")
            Path(tmpdir, "doc2.md").write_text("---\n---\n# Doc 2")
            Path(tmpdir, "README.md").write_text("# Readme")  # Should be excluded

            mock_config.documents_path = Path(tmpdir)
            ingester = DocumentIngester(mock_config)

            files = ingester.scan_documents(Path(tmpdir))
            assert len(files) == 2
            assert all(f.suffix == ".md" for f in files)
            assert not any("README" in str(f) for f in files)


class TestMetadataStore:
    """Tests for MetadataStore with mocked BQ client."""

    @pytest.fixture
    def mock_bq_client(self):
        """Provide a mock BQ client."""
        with patch("cc_coach.rag.metadata.bigquery.Client") as mock:
            client = MagicMock()
            mock.return_value = client
            yield client

    def test_get_document_found(self, mock_bq_client):
        """Should return document when found."""
        from cc_coach.rag.metadata import MetadataStore

        # Mock query result
        mock_row = MagicMock()
        mock_row.__iter__ = lambda self: iter([("uuid", "test-uuid"), ("doc_id", "POL-001")])
        mock_row.keys = lambda: ["uuid", "doc_id"]
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([mock_row])
        mock_bq_client.query.return_value.result.return_value = mock_result

        config = RAGConfig(project_id="test", gcs_bucket="bucket", data_store_id="store")
        store = MetadataStore(config)

        result = store.get_document("test-uuid")
        assert result is not None

    def test_get_document_not_found(self, mock_bq_client):
        """Should return None when document not found."""
        from cc_coach.rag.metadata import MetadataStore

        # Mock empty result
        mock_result = MagicMock()
        mock_result.__iter__ = lambda self: iter([])
        mock_bq_client.query.return_value.result.return_value = mock_result

        config = RAGConfig(project_id="test", gcs_bucket="bucket", data_store_id="store")
        store = MetadataStore(config)

        result = store.get_document("nonexistent-uuid")
        assert result is None


class TestRAGRetriever:
    """Tests for RAGRetriever."""

    def test_extract_uuid_from_uri(self):
        """Should extract UUID from GCS URI."""
        from cc_coach.rag.retriever import RAGRetriever

        config = RAGConfig(project_id="test", gcs_bucket="bucket", data_store_id="store")
        retriever = RAGRetriever(config)

        # Standard UUID format
        uri = "gs://bucket/kb/a1b2c3d4-e5f6-7890-abcd-ef1234567890.md"
        uuid = retriever._extract_uuid_from_uri(uri)
        assert uuid == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        # No UUID found
        uri = "gs://bucket/kb/some-other-file.md"
        uuid = retriever._extract_uuid_from_uri(uri)
        assert uuid == "some-other-file"  # Falls back to filename

    def test_retrieved_document_to_citation(self):
        """Should format citation correctly."""
        from cc_coach.rag.retriever import RetrievedDocument

        doc = RetrievedDocument(
            snippet="Some snippet",
            relevance_score=0.85,
            gcs_uri="gs://bucket/doc.md",
            uuid="test-uuid",
            doc_id="POL-002",
            version="1.1.0",
            title="Prohibited Language Guidelines",
            section="Threats",
        )

        citation = doc.to_citation()
        assert "POL-002" in citation
        assert "v1.1.0" in citation
        assert "Prohibited Language Guidelines" in citation
        assert "Section: Threats" in citation

    def test_retrieval_result_to_context(self):
        """Should format context for LLM prompt."""
        from cc_coach.rag.retriever import RetrievedDocument, RetrievalResult

        docs = [
            RetrievedDocument(
                snippet="Content from doc 1",
                relevance_score=0.9,
                gcs_uri="gs://bucket/doc1.md",
                doc_id="POL-001",
                version="1.0.0",
            ),
            RetrievedDocument(
                snippet="Content from doc 2",
                relevance_score=0.8,
                gcs_uri="gs://bucket/doc2.md",
                doc_id="POL-002",
                version="1.0.0",
            ),
        ]

        result = RetrievalResult(query="test query", documents=docs)
        context = result.to_context()

        assert "POL-001" in context
        assert "POL-002" in context
        assert "Content from doc 1" in context
        assert "Content from doc 2" in context


# =============================================================================
# Topic Extractor Tests
# =============================================================================

class TestTopicExtractor:
    """Tests for TopicExtractor."""

    def test_extract_from_phrase_matches(self):
        """Should extract topics from CI phrase matches."""
        from cc_coach.rag.topic_extractor import TopicExtractor

        extractor = TopicExtractor()
        ci_enrichment = {
            "phrase_matches": [
                {"phrase_matcher_id": "threat_language", "display_name": "Threat Language"},
                {"phrase_matcher_id": "hardship_indicators", "display_name": "Hardship Indicators"},
            ]
        }

        topics = extractor.extract_topics(ci_enrichment=ci_enrichment)

        # Should have topics from both phrase matchers
        assert len(topics) > 0
        assert any("threat" in t.lower() or "prohibited" in t.lower() for t in topics)
        assert any("hardship" in t.lower() for t in topics)

    def test_extract_from_transcript_keywords(self):
        """Should extract topics from transcript keywords."""
        from cc_coach.rag.topic_extractor import TopicExtractor

        extractor = TopicExtractor(include_transcript_keywords=True)
        # Use exact keyword phrase "lost job" from TRANSCRIPT_KEYWORDS
        transcript = [
            {"text": "I lost job last month due to layoffs", "speaker": "CUSTOMER"},
            {"text": "I understand that's difficult", "speaker": "AGENT"},
        ]

        topics = extractor.extract_topics(transcript=transcript)

        # "lost job" should trigger hardship-related topics
        assert len(topics) > 0
        assert any("hardship" in t.lower() for t in topics)

    def test_extract_from_metadata(self):
        """Should extract topics from metadata."""
        from cc_coach.rag.topic_extractor import TopicExtractor

        extractor = TopicExtractor()
        metadata = {
            "business_line": "COLLECTIONS",
            "queue": "hardship_queue",
        }

        topics = extractor.extract_topics(metadata=metadata)

        # Should have collections and hardship topics
        assert len(topics) > 0
        assert any("collection" in t.lower() for t in topics)

    def test_extract_with_details(self):
        """Should return extraction result with sources."""
        from cc_coach.rag.topic_extractor import TopicExtractor

        extractor = TopicExtractor()
        transcript = [{"text": "I need to speak to a supervisor", "speaker": "CUSTOMER"}]

        result = extractor.extract_with_details(transcript=transcript)

        assert hasattr(result, "topics")
        assert hasattr(result, "sources")
        assert len(result.topics) > 0

    def test_max_topics_limit(self):
        """Should limit topics to max_topics."""
        from cc_coach.rag.topic_extractor import TopicExtractor

        extractor = TopicExtractor(max_topics=3)
        ci_enrichment = {
            "phrase_matches": [
                {"phrase_matcher_id": "threat_language", "display_name": "Threat"},
                {"phrase_matcher_id": "hardship_indicators", "display_name": "Hardship"},
                {"phrase_matcher_id": "escalation_request", "display_name": "Escalation"},
            ]
        }
        transcript = [
            {"text": "I'll sue you", "speaker": "CUSTOMER"},
            {"text": "I lost my job", "speaker": "CUSTOMER"},
        ]

        topics = extractor.extract_topics(
            ci_enrichment=ci_enrichment,
            transcript=transcript,
        )

        assert len(topics) <= 3

    def test_empty_input_returns_empty(self):
        """Should return empty list for empty input."""
        from cc_coach.rag.topic_extractor import TopicExtractor

        extractor = TopicExtractor()
        topics = extractor.extract_topics()

        assert topics == []

    def test_deduplication(self):
        """Should return unique topics."""
        from cc_coach.rag.topic_extractor import TopicExtractor

        extractor = TopicExtractor()
        # Both should add "hardship provisions" topic
        ci_enrichment = {
            "phrase_matches": [
                {"phrase_matcher_id": "hardship_indicators", "display_name": "Hardship"},
                {"phrase_matcher_id": "financial_difficulty", "display_name": "Financial"},
            ]
        }

        topics = extractor.extract_topics(ci_enrichment=ci_enrichment)

        # Should have no duplicates
        assert len(topics) == len(set(topics))


# =============================================================================
# RAG Integration Tests
# =============================================================================

class TestCoachingServiceRAGIntegration:
    """Tests for RAG integration in coaching service."""

    def test_coaching_service_accepts_rag_context(self):
        """CoachingService should accept optional rag_context parameter."""
        from cc_coach.agents.conversation_coach import CoachingService

        # Just verify the method signature accepts rag_context
        import inspect
        sig = inspect.signature(CoachingService.analyze_conversation)
        params = list(sig.parameters.keys())
        assert "rag_context" in params

    def test_prompt_templates_exist(self):
        """Should have RAG prompt templates."""
        from cc_coach.prompts.coach_system_prompt import (
            RAG_CONTEXT_TEMPLATE,
            CITATIONS_INSTRUCTION,
        )

        assert "{context}" in RAG_CONTEXT_TEMPLATE
        assert "citations" in CITATIONS_INSTRUCTION.lower()

    def test_coaching_output_has_citation_fields(self):
        """CoachingOutput should have citation fields."""
        from cc_coach.schemas.coaching_output import CoachingOutput
        import pydantic

        fields = CoachingOutput.model_fields
        assert "citations" in fields
        assert "rag_context_used" in fields

    def test_orchestrator_rag_initialization(self):
        """CoachingOrchestrator should initialize RAG components when configured."""
        from cc_coach.services.coaching import CoachingOrchestrator

        # With RAG disabled
        with patch.dict("os.environ", {}, clear=True):
            with patch("cc_coach.services.coaching.BigQueryService"):
                with patch("cc_coach.services.coaching.CoachingService"):
                    orchestrator = CoachingOrchestrator(enable_rag=False)
                    assert orchestrator.rag_enabled is False
                    assert orchestrator.rag_retriever is None

    def test_orchestrator_rag_enabled_with_config(self):
        """CoachingOrchestrator should enable RAG when properly configured."""
        from cc_coach.services.coaching import CoachingOrchestrator

        env = {
            "GCP_PROJECT_ID": "test-project",
            "RAG_GCS_BUCKET": "test-bucket",
            "RAG_DATA_STORE_ID": "test-store",
        }
        with patch.dict("os.environ", env):
            with patch("cc_coach.services.coaching.BigQueryService"):
                with patch("cc_coach.services.coaching.CoachingService"):
                    orchestrator = CoachingOrchestrator(enable_rag=True)
                    assert orchestrator.rag_enabled is True
                    assert orchestrator.rag_retriever is not None
                    assert orchestrator.topic_extractor is not None

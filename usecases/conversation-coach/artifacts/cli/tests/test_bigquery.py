"""Tests for BigQuery service."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from cc_coach.models.registry import ConversationRegistry, RegistryStatus
from cc_coach.services.bigquery import BigQueryService


class TestBigQueryService:
    """Tests for BigQueryService."""

    @pytest.fixture
    def bq_service(self, mock_settings, mock_bigquery_client):
        """Create BigQuery service with mocked client."""
        service = BigQueryService(mock_settings)
        service._client = mock_bigquery_client
        return service

    def test_init(self, mock_settings):
        """Test service initialization."""
        with patch("cc_coach.services.bigquery.bigquery.Client"):
            service = BigQueryService(mock_settings)
            assert service.settings.project_id == "test-project"

    def test_dataset_ref(self, bq_service, mock_settings):
        """Test dataset reference generation."""
        dataset_ref = bq_service.dataset_ref
        assert dataset_ref.project == mock_settings.project_id
        assert dataset_ref.dataset_id == mock_settings.bq_dataset

    def test_table_id(self, bq_service):
        """Test full table ID generation."""
        table_id = bq_service._table_id("conversation_registry")
        assert table_id == "test-project.test_dataset.conversation_registry"

    def test_ensure_dataset_creates_if_not_exists(self, bq_service, mock_bigquery_client):
        """Test dataset creation when it doesn't exist."""
        from google.cloud.exceptions import NotFound

        mock_bigquery_client.get_dataset.side_effect = NotFound("Dataset not found")
        mock_bigquery_client.create_dataset.return_value = MagicMock()

        bq_service.ensure_dataset()

        mock_bigquery_client.create_dataset.assert_called_once()

    def test_ensure_dataset_skips_if_exists(self, bq_service, mock_bigquery_client):
        """Test that existing dataset is not recreated."""
        mock_bigquery_client.get_dataset.return_value = MagicMock()

        bq_service.ensure_dataset()

        mock_bigquery_client.create_dataset.assert_not_called()

    def test_ensure_table_creates_if_not_exists(self, bq_service, mock_bigquery_client):
        """Test table creation when it doesn't exist."""
        from google.cloud.exceptions import NotFound

        mock_bigquery_client.get_table.side_effect = NotFound("Table not found")
        mock_bigquery_client.create_table.return_value = MagicMock()

        from cc_coach.services.bigquery import REGISTRY_SCHEMA

        bq_service.ensure_table("test_table", REGISTRY_SCHEMA)

        mock_bigquery_client.create_table.assert_called_once()

    def test_upsert_registry(self, bq_service, mock_bigquery_client, sample_registry):
        """Test registry UPSERT operation."""
        mock_query = MagicMock()
        mock_bigquery_client.query.return_value = mock_query
        mock_query.result.return_value = None

        bq_service.upsert_registry(sample_registry)

        mock_bigquery_client.query.assert_called_once()
        # Verify MERGE query was used
        call_args = mock_bigquery_client.query.call_args
        assert "MERGE" in call_args[0][0]

    def test_get_registry_found(self, bq_service, mock_bigquery_client):
        """Test getting an existing registry entry."""
        mock_row = {
            "conversation_id": "test-uuid",
            "status": "NEW",
            "has_transcript": True,
            "has_metadata": True,
            "has_audio": False,
            "created_at": datetime(2025, 1, 1),
            "updated_at": datetime(2025, 1, 1),
        }

        mock_query = MagicMock()
        mock_bigquery_client.query.return_value = mock_query
        mock_query.result.return_value = [mock_row]

        result = bq_service.get_registry("test-uuid")

        assert result is not None
        assert result.conversation_id == "test-uuid"
        assert result.status == RegistryStatus.NEW

    def test_get_registry_not_found(self, bq_service, mock_bigquery_client):
        """Test getting a non-existent registry entry."""
        mock_query = MagicMock()
        mock_bigquery_client.query.return_value = mock_query
        mock_query.result.return_value = []

        result = bq_service.get_registry("non-existent-uuid")

        assert result is None

    def test_list_registry_with_status_filter(self, bq_service, mock_bigquery_client):
        """Test listing registry entries with status filter."""
        mock_query = MagicMock()
        mock_bigquery_client.query.return_value = mock_query
        mock_query.result.return_value = []

        bq_service.list_registry(status=RegistryStatus.ENRICHED)

        # Verify status filter was included in query
        call_args = mock_bigquery_client.query.call_args
        assert "status = @status" in call_args[0][0]

    def test_get_status_counts(self, bq_service, mock_bigquery_client):
        """Test getting status counts."""
        mock_rows = [
            {"status": "NEW", "count": 10},
            {"status": "ENRICHED", "count": 5},
        ]

        mock_query = MagicMock()
        mock_bigquery_client.query.return_value = mock_query
        mock_query.result.return_value = mock_rows

        counts = bq_service.get_status_counts()

        assert counts["NEW"] == 10
        assert counts["ENRICHED"] == 5

    def test_query_execution(self, bq_service, mock_bigquery_client):
        """Test arbitrary SQL query execution."""
        mock_rows = [{"col1": "val1", "col2": 123}]

        mock_query = MagicMock()
        mock_bigquery_client.query.return_value = mock_query
        mock_query.result.return_value = mock_rows

        results = bq_service.query("SELECT * FROM test")

        assert len(results) == 1
        assert results[0]["col1"] == "val1"

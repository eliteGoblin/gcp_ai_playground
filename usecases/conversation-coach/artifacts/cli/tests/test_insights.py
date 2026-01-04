"""Tests for CCAI Insights service."""

from unittest.mock import MagicMock, patch

import pytest

from cc_coach.services.insights import InsightsService


class TestInsightsService:
    """Tests for InsightsService."""

    @pytest.fixture
    def mock_storage_for_insights(self):
        """Mock storage client for insights service."""
        with patch("cc_coach.services.insights.storage.Client") as mock:
            client = MagicMock()
            mock.return_value = client
            # Setup bucket and blob mocks
            mock_bucket = MagicMock()
            mock_blob = MagicMock()
            client.bucket.return_value = mock_bucket
            mock_bucket.blob.return_value = mock_blob
            yield client

    @pytest.fixture
    def insights_service(self, mock_settings, mock_insights_client, mock_storage_for_insights):
        """Create Insights service with mocked clients."""
        service = InsightsService(mock_settings)
        service._client = mock_insights_client
        service._storage = mock_storage_for_insights
        return service

    def test_init(self, mock_settings):
        """Test service initialization."""
        with patch("cc_coach.services.insights.insights.ContactCenterInsightsClient"):
            service = InsightsService(mock_settings)
            assert service.settings.project_id == "test-project"

    def test_parent_path(self, insights_service, mock_settings):
        """Test parent resource path generation."""
        assert insights_service.parent == f"projects/{mock_settings.project_id}/locations/{mock_settings.insights_location}"

    def test_create_conversation(self, insights_service, mock_insights_client, sample_conversation):
        """Test creating a conversation in CCAI Insights."""
        mock_created = MagicMock()
        mock_created.name = "projects/test/locations/us-central1/conversations/test-uuid"
        mock_insights_client.create_conversation.return_value = mock_created

        result = insights_service.create_conversation(sample_conversation)

        mock_insights_client.create_conversation.assert_called_once()
        assert result.name == "projects/test/locations/us-central1/conversations/test-uuid"

    def test_create_conversation_with_custom_id(self, insights_service, mock_insights_client, sample_conversation):
        """Test creating a conversation with custom ID."""
        mock_created = MagicMock()
        mock_created.name = "projects/test/locations/us-central1/conversations/custom-id"
        mock_insights_client.create_conversation.return_value = mock_created

        result = insights_service.create_conversation(sample_conversation, conversation_id="custom-id")

        call_args = mock_insights_client.create_conversation.call_args
        assert call_args.kwargs["request"].conversation_id == "custom-id"

    def test_get_conversation_found(self, insights_service, mock_insights_client):
        """Test getting an existing conversation."""
        mock_conv = MagicMock()
        mock_conv.name = "projects/test/locations/us-central1/conversations/test-uuid"
        mock_insights_client.get_conversation.return_value = mock_conv

        result = insights_service.get_conversation(mock_conv.name)

        assert result is not None
        assert result.name == mock_conv.name

    def test_get_conversation_not_found(self, insights_service, mock_insights_client):
        """Test getting a non-existent conversation."""
        mock_insights_client.get_conversation.side_effect = Exception("Not found")

        result = insights_service.get_conversation("projects/test/locations/us-central1/conversations/missing")

        assert result is None

    def test_create_analysis(self, insights_service, mock_insights_client):
        """Test triggering analysis on a conversation."""
        mock_operation = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.name = "projects/test/locations/us-central1/conversations/test/analyses/analysis-1"
        mock_operation.result.return_value = mock_analysis
        mock_insights_client.create_analysis.return_value = mock_operation

        result = insights_service.create_analysis("projects/test/locations/us-central1/conversations/test")

        mock_insights_client.create_analysis.assert_called_once()
        assert result.name == mock_analysis.name

    def test_list_conversations(self, insights_service, mock_insights_client):
        """Test listing conversations."""
        mock_conv1 = MagicMock()
        mock_conv1.name = "projects/test/conversations/1"
        mock_conv2 = MagicMock()
        mock_conv2.name = "projects/test/conversations/2"

        mock_insights_client.list_conversations.return_value = [mock_conv1, mock_conv2]

        result = insights_service.list_conversations()

        assert len(result) == 2

    def test_list_conversations_with_filter(self, insights_service, mock_insights_client):
        """Test listing conversations with filter."""
        mock_insights_client.list_conversations.return_value = []

        insights_service.list_conversations(filter_str='labels.business_line="COLLECTIONS"')

        call_args = mock_insights_client.list_conversations.call_args
        assert call_args.kwargs["request"].filter == 'labels.business_line="COLLECTIONS"'

    def test_ingest_conversation(self, insights_service, mock_insights_client, sample_conversation):
        """Test complete ingestion workflow."""
        mock_created = MagicMock()
        mock_created.name = "projects/test/conversations/test-uuid"
        mock_insights_client.create_conversation.return_value = mock_created

        mock_operation = MagicMock()
        mock_analysis = MagicMock()
        mock_analysis.name = "projects/test/conversations/test-uuid/analyses/1"
        mock_operation.result.return_value = mock_analysis
        mock_insights_client.create_analysis.return_value = mock_operation

        result = insights_service.ingest_conversation(sample_conversation, run_analysis=True)

        assert result["conversation_name"] == mock_created.name
        assert result["analysis_name"] == mock_analysis.name
        assert result["status"] == "analyzed"

    def test_ingest_conversation_skip_analysis(self, insights_service, mock_insights_client, sample_conversation):
        """Test ingestion without analysis."""
        mock_created = MagicMock()
        mock_created.name = "projects/test/conversations/test-uuid"
        mock_insights_client.create_conversation.return_value = mock_created

        result = insights_service.ingest_conversation(sample_conversation, run_analysis=False)

        mock_insights_client.create_analysis.assert_not_called()
        assert result["status"] == "created"
        assert result["analysis_name"] is None

    def test_delete_conversation(self, insights_service, mock_insights_client):
        """Test deleting a conversation."""
        mock_insights_client.delete_conversation.return_value = None

        result = insights_service.delete_conversation("projects/test/conversations/test-uuid")

        mock_insights_client.delete_conversation.assert_called_once()
        assert result is True

    def test_delete_conversation_failure(self, insights_service, mock_insights_client):
        """Test delete failure handling."""
        mock_insights_client.delete_conversation.side_effect = Exception("Delete failed")

        result = insights_service.delete_conversation("projects/test/conversations/test-uuid")

        assert result is False

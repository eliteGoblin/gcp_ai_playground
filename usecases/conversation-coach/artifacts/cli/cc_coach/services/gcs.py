"""
GCS service for Conversation Coach.

Handles loading conversation data from GCS buckets.
"""

import json
import logging
from pathlib import Path
from typing import Iterator, Optional

from google.cloud import storage

from cc_coach.config import Settings, get_settings
from cc_coach.models.conversation import (
    Conversation,
    ConversationMetadata,
    Transcription,
)

logger = logging.getLogger(__name__)


class GCSService:
    """Service for GCS operations."""

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize GCS service."""
        self.settings = settings or get_settings()
        self._client: Optional[storage.Client] = None

    @property
    def client(self) -> storage.Client:
        """Lazy-load GCS client."""
        if self._client is None:
            self._client = storage.Client(project=self.settings.project_id)
        return self._client

    def get_bucket(self, bucket_name: Optional[str] = None) -> storage.Bucket:
        """Get bucket by name."""
        name = bucket_name or self.settings.gcs_bucket_dev
        return self.client.bucket(name)

    def list_conversation_ids(
        self,
        date_folder: str,
        bucket_name: Optional[str] = None,
    ) -> list[str]:
        """
        List all conversation IDs in a date folder.

        Args:
            date_folder: Date folder like "2025-12-28"
            bucket_name: Optional bucket name override

        Returns:
            List of conversation UUIDs
        """
        bucket = self.get_bucket(bucket_name)
        prefix = f"{date_folder}/"

        # Get unique conversation IDs from folder structure
        conversation_ids = set()
        blobs = bucket.list_blobs(prefix=prefix)

        for blob in blobs:
            # Path format: 2025-12-28/<UUID>/metadata.json
            parts = blob.name.split("/")
            if len(parts) >= 2:
                conversation_ids.add(parts[1])

        return sorted(conversation_ids)

    def load_conversation(
        self,
        date_folder: str,
        conversation_id: str,
        bucket_name: Optional[str] = None,
    ) -> Optional[Conversation]:
        """
        Load a complete conversation from GCS.

        Args:
            date_folder: Date folder like "2025-12-28"
            conversation_id: Conversation UUID
            bucket_name: Optional bucket name override

        Returns:
            Conversation object or None if not found
        """
        bucket = self.get_bucket(bucket_name)
        prefix = f"{date_folder}/{conversation_id}/"

        transcription_blob = bucket.blob(f"{prefix}transcription.json")
        metadata_blob = bucket.blob(f"{prefix}metadata.json")

        try:
            transcription_data = json.loads(transcription_blob.download_as_text())
            metadata_data = json.loads(metadata_blob.download_as_text())
        except Exception as e:
            logger.warning(f"Failed to load conversation {conversation_id}: {e}")
            return None

        try:
            transcription = Transcription(**transcription_data)
            metadata = ConversationMetadata(**metadata_data)
            return Conversation(transcription=transcription, metadata=metadata)
        except Exception as e:
            logger.error(f"Failed to parse conversation {conversation_id}: {e}")
            return None

    def iter_conversations(
        self,
        date_folder: str,
        bucket_name: Optional[str] = None,
    ) -> Iterator[Conversation]:
        """
        Iterate over all conversations in a date folder.

        Args:
            date_folder: Date folder like "2025-12-28"
            bucket_name: Optional bucket name override

        Yields:
            Conversation objects
        """
        conversation_ids = self.list_conversation_ids(date_folder, bucket_name)
        logger.info(f"Found {len(conversation_ids)} conversations in {date_folder}")

        for conv_id in conversation_ids:
            conversation = self.load_conversation(date_folder, conv_id, bucket_name)
            if conversation:
                yield conversation

    def get_gcs_uri(
        self,
        date_folder: str,
        conversation_id: str,
        filename: str,
        bucket_name: Optional[str] = None,
    ) -> str:
        """Get GCS URI for a conversation file."""
        name = bucket_name or self.settings.gcs_bucket_dev
        return f"gs://{name}/{date_folder}/{conversation_id}/{filename}"


class LocalDataService:
    """
    Service for loading conversation data from local filesystem.

    Used for development and testing without GCS access.
    """

    def __init__(self, data_dir: Path):
        """Initialize with local data directory."""
        self.data_dir = data_dir

    def list_conversation_ids(self, date_folder: str) -> list[str]:
        """List conversation IDs in a local date folder."""
        folder = self.data_dir / date_folder
        if not folder.exists():
            return []

        return sorted([
            d.name for d in folder.iterdir()
            if d.is_dir() and (d / "transcription.json").exists()
        ])

    def load_conversation(
        self,
        date_folder: str,
        conversation_id: str,
    ) -> Optional[Conversation]:
        """Load a conversation from local filesystem."""
        folder = self.data_dir / date_folder / conversation_id

        transcription_file = folder / "transcription.json"
        metadata_file = folder / "metadata.json"

        if not transcription_file.exists() or not metadata_file.exists():
            return None

        try:
            transcription_data = json.loads(transcription_file.read_text())
            metadata_data = json.loads(metadata_file.read_text())

            transcription = Transcription(**transcription_data)
            metadata = ConversationMetadata(**metadata_data)
            return Conversation(transcription=transcription, metadata=metadata)
        except Exception as e:
            logger.error(f"Failed to parse conversation {conversation_id}: {e}")
            return None

    def iter_conversations(self, date_folder: str) -> Iterator[Conversation]:
        """Iterate over conversations in a local date folder."""
        for conv_id in self.list_conversation_ids(date_folder):
            conversation = self.load_conversation(date_folder, conv_id)
            if conversation:
                yield conversation

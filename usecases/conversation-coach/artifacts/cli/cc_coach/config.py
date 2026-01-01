"""
Configuration management using Pydantic Settings.

Supports environment variables and .env files for configuration.
Designed to work both locally and in Cloud Run.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CC_",
        case_sensitive=False,
    )

    # GCP Project
    project_id: str = Field(
        default="vertexdemo-481519",
        description="GCP Project ID",
    )
    region: str = Field(
        default="us-central1",
        description="GCP Region for CCAI Insights",
    )

    # GCS
    gcs_bucket_dev: str = Field(
        default="vertexdemo-481519-cc-dev",
        description="GCS bucket for dev data",
    )

    # BigQuery
    bq_dataset: str = Field(
        default="conversation_coach",
        description="BigQuery dataset name",
    )
    bq_location: str = Field(
        default="US",
        description="BigQuery dataset location",
    )

    # CCAI Insights
    insights_location: str = Field(
        default="us-central1",
        description="CCAI Insights location",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )

    # Feature flags
    dry_run: bool = Field(
        default=False,
        description="If True, don't make actual API calls",
    )

    @property
    def insights_parent(self) -> str:
        """CCAI Insights parent resource path."""
        return f"projects/{self.project_id}/locations/{self.insights_location}"

    @property
    def bq_dataset_id(self) -> str:
        """Full BigQuery dataset ID."""
        return f"{self.project_id}.{self.bq_dataset}"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

"""
Configuration architecture for n8n MCP Server.
Implements typed, validated settings using Pydantic Settings v2.
"""

from __future__ import annotations
from typing import Dict
from pydantic import Field, AliasChoices, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class N8nConfig(BaseSettings):
    """Production configuration schema for n8n Model Context Protocol Server."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    n8n_host: str = Field(
        default="http://localhost:5678",
        validation_alias=AliasChoices("n8n_host", "N8N_HOST"),
        description="Base URL for target n8n instance",
    )
    n8n_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("n8n_api_key", "N8N_API_KEY"),
        description="Public REST API Key for n8n authentication",
    )
    timeout_seconds: float = Field(
        default=30.0,
        validation_alias=AliasChoices("n8n_timeout_seconds", "timeout_seconds", "TIMEOUT_SECONDS"),
        description="HTTP request timeout in seconds",
    )
    max_retries: int = Field(
        default=3,
        validation_alias=AliasChoices("n8n_max_retries", "max_retries", "MAX_RETRIES"),
        description="Maximum retry attempts with full-jitter exponential backoff",
    )
    behavioral_playwright_url: str = Field(
        default="http://host.docker.internal:8000",
        validation_alias=AliasChoices("behavioral_playwright_url", "BEHAVIORAL_PLAYWRIGHT_URL"),
        description="Host URL for behavioral-playwright scraping facade",
    )
    snapshots_dir: str = Field(
        default=".snapshots",
        validation_alias=AliasChoices("n8n_snapshots_dir", "snapshots_dir", "SNAPSHOTS_DIR"),
        description="Local directory for rollback workflow snapshots",
    )

    @field_validator("n8n_host", "behavioral_playwright_url", mode="after")
    @classmethod
    def normalize_urls(cls, value: str) -> str:
        """Strip trailing slashes for reliable endpoint concatenation."""
        return value.rstrip("/") if value else value

    @property
    def api_url(self) -> str:
        """Returns the base public REST API v1 endpoint."""
        return f"{self.n8n_host}/api/v1"

    @property
    def auth_headers(self) -> Dict[str, str]:
        """Generates standard n8n authentication headers if API key is configured."""
        if self.n8n_api_key:
            return {"X-N8N-API-KEY": self.n8n_api_key}
        return {}

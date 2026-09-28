"""
Unit tests for N8nConfig configuration architecture.
Testing defaults, environment variable overrides, URL normalizations, and convenience properties.
"""

import pytest
from n8n_mcp.config import N8nConfig


def test_default_config():
    """Verify production-grade defaults."""
    config = N8nConfig()
    assert config.n8n_host == "http://localhost:5678"
    assert config.n8n_api_key == ""
    assert config.timeout_seconds == 30.0
    assert config.max_retries == 3
    assert config.behavioral_playwright_url == "http://host.docker.internal:8000"
    assert config.snapshots_dir == ".snapshots"
    assert config.api_url == "http://localhost:5678/api/v1"
    assert config.auth_headers == {}


def test_url_trailing_slash_normalization():
    """Verify that trailing slashes are cleanly stripped from host URLs."""
    config = N8nConfig(
        n8n_host="https://n8n.workflow-corp.com///",
        behavioral_playwright_url="http://localhost:8000/",
    )
    assert config.n8n_host == "https://n8n.workflow-corp.com"
    assert config.api_url == "https://n8n.workflow-corp.com/api/v1"
    assert config.behavioral_playwright_url == "http://localhost:8000"


def test_auth_headers_generation():
    """Verify auth headers generation when API key is provided."""
    config = N8nConfig(n8n_api_key="secret-n8n-token-xyz")
    assert config.auth_headers == {"X-N8N-API-KEY": "secret-n8n-token-xyz"}


def test_environment_variable_override(monkeypatch):
    """Verify environment variables override defaults."""
    monkeypatch.setenv("N8N_HOST", "https://cloud.n8n.io/")
    monkeypatch.setenv("N8N_API_KEY", "env-api-key-456")
    monkeypatch.setenv("N8N_TIMEOUT_SECONDS", "45.5")
    monkeypatch.setenv("N8N_MAX_RETRIES", "5")
    monkeypatch.setenv("BEHAVIORAL_PLAYWRIGHT_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("N8N_SNAPSHOTS_DIR", "custom_snapshots")

    config = N8nConfig()
    assert config.n8n_host == "https://cloud.n8n.io"
    assert config.n8n_api_key == "env-api-key-456"
    assert config.timeout_seconds == 45.5
    assert config.max_retries == 5
    assert config.behavioral_playwright_url == "http://127.0.0.1:8000"
    assert config.snapshots_dir == "custom_snapshots"
    assert config.api_url == "https://cloud.n8n.io/api/v1"
    assert config.auth_headers == {"X-N8N-API-KEY": "env-api-key-456"}

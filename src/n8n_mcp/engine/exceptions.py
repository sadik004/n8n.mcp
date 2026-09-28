"""
Domain exception hierarchy for n8n MCP Server operations.
"""

from typing import Optional


class N8nClientError(Exception):
    """Base exception for all n8n client communication failures."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class N8nAuthError(N8nClientError):
    """Raised when n8n rejects API key or authentication credentials (HTTP 401/403)."""


class N8nNotFoundError(N8nClientError):
    """Raised when a requested workflow, execution, or node is not found (HTTP 404)."""


class N8nRateLimitError(N8nClientError):
    """Raised when n8n or an upstream proxy responds with HTTP 429 Too Many Requests."""


class N8nValidationError(N8nClientError):
    """Raised when n8n rejects request body due to malformed schema (HTTP 400)."""

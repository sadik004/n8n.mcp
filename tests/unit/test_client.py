"""
Unit tests for resilient N8nClient using httpx.MockTransport.
Testing authentication, payload sanitization, backoff logic, workflow CRUD, executions, webhooks, and template API.
"""

import json
import pytest
import httpx
from n8n_mcp.config import N8nConfig
from n8n_mcp.engine.client import N8nClient
from n8n_mcp.engine.exceptions import (
    N8nAuthError,
    N8nNotFoundError,
    N8nRateLimitError,
    N8nValidationError,
)
from n8n_mcp.models.workflow import WorkflowDTO, WorkflowSanitizedPayload


@pytest.fixture
def base_config():
    return N8nConfig(
        n8n_host="http://localhost:5678",
        n8n_api_key="test-api-token",
        timeout_seconds=5.0,
        max_retries=2,
    )


@pytest.mark.asyncio
async def test_auth_headers_and_error_handling(base_config):
    """Verify 401/403 triggers N8nAuthError and 404 triggers N8nNotFoundError."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-N8N-API-KEY") == "test-api-token"
        if "workflows/wf-404" in str(request.url):
            return httpx.Response(404, json={"message": "Workflow not found"})
        elif "workflows/wf-unauth" in str(request.url):
            return httpx.Response(401, json={"message": "Unauthorized access"})
        return httpx.Response(200, json={"data": []})

    transport = httpx.MockTransport(handler)
    client = N8nClient(config=base_config, transport=transport)

    with pytest.raises(N8nNotFoundError):
        await client.get_workflow("wf-404")

    with pytest.raises(N8nAuthError):
        await client.get_workflow("wf-unauth")

    await client.aclose()


@pytest.mark.asyncio
async def test_sanitize_workflow_payload_in_update(base_config):
    """Verify update_workflow strictly sanitizes payload, stripping read-only fields."""
    captured_payload = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        if request.method == "PUT" and "workflows/wf-100" in str(request.url):
            captured_payload = json.loads(request.content.decode("utf-8"))
            return httpx.Response(
                200,
                json={
                    "id": "wf-100",
                    "name": captured_payload.get("name"),
                    "nodes": captured_payload.get("nodes", []),
                    "connections": captured_payload.get("connections", {}),
                    "active": False,
                },
            )
        return httpx.Response(400, json={"message": "Unexpected endpoint"})

    transport = httpx.MockTransport(handler)
    client = N8nClient(config=base_config, transport=transport)

    # Input dirty payload with read-only fields
    dirty_payload = {
        "id": "wf-100",
        "name": "Clean Workflow",
        "versionId": "v123",
        "createdAt": "2026-09-28T00:00:00Z",
        "triggerCount": 9,
        "nodes": [{"name": "Code", "type": "n8n-nodes-base.code", "parameters": {}}],
        "connections": {},
        "settings": {"saveExecutionProgress": True},
    }

    result = await client.update_workflow("wf-100", dirty_payload)
    assert result.id == "wf-100"
    assert result.name == "Clean Workflow"

    # Verify captured PUT payload has ONLY mutable keys
    assert captured_payload["name"] == "Clean Workflow"
    assert "nodes" in captured_payload
    assert "connections" in captured_payload
    assert "settings" in captured_payload
    for forbidden in ("id", "versionId", "createdAt", "triggerCount"):
        assert forbidden not in captured_payload

    await client.aclose()


@pytest.mark.asyncio
async def test_webhook_trigger_test_vs_prod_path(base_config):
    """Verify test webhook maps to /webhook-test/ and production maps to /webhook/."""
    requested_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, json={"received": True, "path": str(request.url)})

    transport = httpx.MockTransport(handler)
    client = N8nClient(config=base_config, transport=transport)

    # 1. Test webhook
    await client.trigger_webhook("custom-lead-event", is_test=True, payload={"lead_id": "abc"})
    assert requested_urls[-1] == "http://localhost:5678/webhook-test/custom-lead-event"

    # 2. Production webhook
    await client.trigger_webhook("/stripe/payment-hook/", is_test=False, payload={"amount": 100})
    assert requested_urls[-1] == "http://localhost:5678/webhook/stripe/payment-hook"

    await client.aclose()


@pytest.mark.asyncio
async def test_retry_on_429_rate_limit(base_config):
    """Verify automatic retry with backoff on HTTP 429."""
    attempt_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 2:
            return httpx.Response(429, json={"message": "Too Many Requests"})
        return httpx.Response(200, json={"status": "ok", "version": "1.80.0"})

    transport = httpx.MockTransport(handler)
    client = N8nClient(config=base_config, transport=transport)

    health = await client.health_check()
    assert health["status"] == "healthy"
    assert health["api_connected"] is True
    assert attempt_count == 2

    await client.aclose()

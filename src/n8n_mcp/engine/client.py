"""
Resilient asynchronous n8n Public REST API and Webhook client.
Equipped with AWS Full-Jitter Exponential Backoff, payload sanitization (anti-HTTP 400), and connection pooling.
"""

from __future__ import annotations
import asyncio
import json
import logging
import random
from typing import Any, Dict, List, Optional
import httpx

from n8n_mcp.config import N8nConfig
from n8n_mcp.engine.exceptions import (
    N8nClientError,
    N8nAuthError,
    N8nNotFoundError,
    N8nRateLimitError,
    N8nValidationError,
)
from n8n_mcp.models.workflow import (
    WorkflowDTO,
    WorkflowSanitizedPayload,
    WorkflowCreateRequest,
    WorkflowUpdateRequest,
    WorkflowListResponse,
)
from n8n_mcp.models.execution import (
    ExecutionDTO,
    ExecutionDetailDTO,
    ExecutionListResponse,
)
from n8n_mcp.models.template import TemplateSummaryDTO, TemplateDetailDTO

logger = logging.getLogger("n8n_mcp.client")


class N8nClient:
    """Production client orchestrating n8n REST operations with jittered retries and sanitization."""

    MUTABLE_WORKFLOW_KEYS = {"name", "nodes", "connections", "settings", "pinData", "pin_data"}

    def __init__(
        self,
        config: Optional[N8nConfig] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.config = config or N8nConfig()
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
        self.client = httpx.AsyncClient(
            transport=transport,
            timeout=self.config.timeout_seconds,
            limits=limits,
        )

    async def aclose(self) -> None:
        """Close underlying HTTP client connections."""
        await self.client.aclose()

    async def __aenter__(self) -> N8nClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.aclose()

    @classmethod
    def sanitize_workflow_payload(cls, payload: Dict[str, Any] | WorkflowDTO) -> Dict[str, Any]:
        """
        Strips read-only metadata to prevent n8n HTTP 400 Bad Request: Malformed Data errors.
        Retains strictly: name, nodes, connections, settings, pinData.
        """
        if isinstance(payload, WorkflowDTO):
            return WorkflowSanitizedPayload.from_workflow(payload).to_api_dict()

        sanitized: Dict[str, Any] = {
            "name": payload.get("name", "Untitled Workflow"),
            "nodes": payload.get("nodes", []),
            "connections": payload.get("connections", {}),
            "settings": payload.get("settings", {}),
        }

        pin_data = payload.get("pinData") or payload.get("pin_data")
        if pin_data is not None:
            sanitized["pinData"] = pin_data

        return sanitized

    def _calculate_jitter_backoff(
        self, attempt: int, base_delay: float = 0.5, max_delay: float = 10.0
    ) -> float:
        """Computes AWS Full-Jitter delay: random.uniform(0, min(max_delay, base_delay * 2^attempt))."""
        exponential_ceiling = min(max_delay, base_delay * (2 ** attempt))
        return random.uniform(0.1, exponential_ceiling)

    async def _request(
        self,
        method: str,
        url_or_endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        custom_headers: Optional[Dict[str, str]] = None,
        is_full_url: bool = False,
    ) -> httpx.Response:
        """Executes HTTP request with AWS Full-Jitter retry policy on 429 and 503."""
        if is_full_url:
            target_url = url_or_endpoint
        else:
            clean_endpoint = url_or_endpoint.lstrip("/")
            target_url = f"{self.config.api_url}/{clean_endpoint}"

        headers = {**self.config.auth_headers, **(custom_headers or {})}

        last_response: Optional[httpx.Response] = None
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self.client.request(
                    method=method,
                    url=target_url,
                    params=params,
                    json=json_data,
                    headers=headers,
                )
                last_response = response

                if response.status_code in (429, 503) and attempt < self.config.max_retries:
                    sleep_time = self._calculate_jitter_backoff(attempt)
                    logger.warning(
                        f"Rate limit / Service unavailable ({response.status_code}) on {target_url}. "
                        f"Retrying in {sleep_time:.2f}s (Attempt {attempt + 1}/{self.config.max_retries})"
                    )
                    await asyncio.sleep(sleep_time)
                    continue

                if response.status_code == 401 or response.status_code == 403:
                    raise N8nAuthError(f"Authentication failed: {response.text}", status_code=response.status_code)
                elif response.status_code == 404:
                    raise N8nNotFoundError(f"Resource not found at {target_url}: {response.text}", status_code=404)
                elif response.status_code == 400:
                    raise N8nValidationError(f"Validation error (HTTP 400): {response.text}", status_code=400)
                elif response.status_code == 429:
                    raise N8nRateLimitError(f"Rate limit exceeded: {response.text}", status_code=429)

                response.raise_for_status()
                return response

            except (httpx.ConnectError, httpx.TimeoutException) as net_err:
                if attempt < self.config.max_retries:
                    sleep_time = self._calculate_jitter_backoff(attempt)
                    logger.warning(f"Network error ({net_err}) on {target_url}. Retrying in {sleep_time:.2f}s")
                    await asyncio.sleep(sleep_time)
                    continue
                raise N8nClientError(f"Connection to n8n failed after {attempt} retries: {net_err}") from net_err

        if last_response is not None:
            last_response.raise_for_status()
            return last_response
        raise N8nClientError(f"Request failed unexpectedly to {target_url}")

    # =========================================================================
    # WORKFLOW MANAGEMENT
    # =========================================================================

    async def list_workflows(
        self,
        active: Optional[bool] = None,
        tags: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> WorkflowListResponse:
        """Fetch list of workflows from n8n."""
        params: Dict[str, Any] = {"limit": limit}
        if active is not None:
            params["active"] = str(active).lower()
        if tags:
            params["tags"] = tags
        if cursor:
            params["cursor"] = cursor

        resp = await self._request("GET", "workflows", params=params)
        return WorkflowListResponse.model_validate(resp.json())

    async def get_workflow(self, workflow_id: str) -> WorkflowDTO:
        """Fetch complete workflow definition by ID."""
        resp = await self._request("GET", f"workflows/{workflow_id}")
        return WorkflowDTO.model_validate(resp.json())

    async def create_workflow(
        self,
        payload: Dict[str, Any] | WorkflowCreateRequest | WorkflowSanitizedPayload,
    ) -> WorkflowDTO:
        """Create a new workflow with sanitized payload."""
        if isinstance(payload, WorkflowSanitizedPayload):
            body = payload.to_api_dict()
        else:
            raw_dict = payload if isinstance(payload, dict) else payload.model_dump(by_alias=True)
            body = self.sanitize_workflow_payload(raw_dict)

        resp = await self._request("POST", "workflows", json_data=body)
        return WorkflowDTO.model_validate(resp.json())

    async def update_workflow(
        self,
        workflow_id: str,
        payload: Dict[str, Any] | WorkflowUpdateRequest | WorkflowSanitizedPayload,
    ) -> WorkflowDTO:
        """Replace workflow definition with sanitized payload, preventing HTTP 400 errors."""
        if isinstance(payload, WorkflowSanitizedPayload):
            body = payload.to_api_dict()
        else:
            raw_dict = payload if isinstance(payload, dict) else payload.model_dump(by_alias=True)
            body = self.sanitize_workflow_payload(raw_dict)

        resp = await self._request("PUT", f"workflows/{workflow_id}", json_data=body)
        return WorkflowDTO.model_validate(resp.json())

    async def activate_workflow(self, workflow_id: str, active: bool = True) -> WorkflowDTO:
        """Toggle workflow active state via n8n activation endpoints."""
        action = "activate" if active else "deactivate"
        resp = await self._request("POST", f"workflows/{workflow_id}/{action}")
        return WorkflowDTO.model_validate(resp.json())

    async def delete_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Permanently delete a workflow."""
        resp = await self._request("DELETE", f"workflows/{workflow_id}")
        return resp.json() if resp.text else {"success": True, "id": workflow_id}

    # =========================================================================
    # EXECUTIONS & RUNTIME
    # =========================================================================

    async def list_executions(
        self,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
        cursor: Optional[str] = None,
    ) -> ExecutionListResponse:
        """Query execution history with status and workflow filters."""
        params: Dict[str, Any] = {"limit": limit}
        if workflow_id:
            params["workflowId"] = workflow_id
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor

        resp = await self._request("GET", "executions", params=params)
        return ExecutionListResponse.model_validate(resp.json())

    async def get_execution(self, execution_id: str, include_data: bool = True) -> ExecutionDetailDTO:
        """Fetch detailed execution trace and node outputs."""
        params = {"includeData": "true"} if include_data else {}
        resp = await self._request("GET", f"executions/{execution_id}", params=params)
        return ExecutionDetailDTO.model_validate(resp.json())

    async def retry_execution(self, execution_id: str, load_workflow: bool = True) -> Dict[str, Any]:
        """Retry a failed execution by ID."""
        resp = await self._request(
            "POST",
            f"executions/{execution_id}/retry",
            json_data={"loadWorkflow": load_workflow},
        )
        return resp.json()

    async def delete_execution(self, execution_id: str) -> Dict[str, Any]:
        """Delete an execution record from history."""
        resp = await self._request("DELETE", f"executions/{execution_id}")
        return resp.json() if resp.text else {"success": True, "id": execution_id}

    # =========================================================================
    # WEBHOOKS & TESTING TRIGGERS
    # =========================================================================

    async def trigger_webhook(
        self,
        path: str,
        is_test: bool = True,
        method: str = "POST",
        payload: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Trigger an n8n webhook.
        When is_test=True, routes to /webhook-test/{path} (canvas test listener).
        When is_test=False, routes to /webhook/{path} (production active listener).
        """
        clean_path = path.strip("/")
        route_prefix = "webhook-test" if is_test else "webhook"
        target_url = f"{self.config.n8n_host}/{route_prefix}/{clean_path}"

        resp = await self._request(
            method=method.upper(),
            url_or_endpoint=target_url,
            params=params,
            json_data=payload,
            custom_headers=headers,
            is_full_url=True,
        )
        try:
            return resp.json()
        except Exception:
            return {"status_code": resp.status_code, "text": resp.text}

    # =========================================================================
    # TEMPLATES DISCOVERY (api.n8n.io)
    # =========================================================================

    async def search_templates(self, query: str, page: int = 1, limit: int = 20) -> List[TemplateSummaryDTO]:
        """Search official & community n8n template library."""
        url = f"https://api.n8n.io/api/templates/workflows?search={query}&page={page}&limit={limit}"
        try:
            resp = await self.client.get(url, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("workflows") or data.get("data") or []
            return [TemplateSummaryDTO.model_validate(item) for item in items]
        except Exception as exc:
            logger.warning(f"Could not reach n8n template registry: {exc}")
            return []

    async def get_template(self, template_id: int | str) -> Optional[TemplateDetailDTO]:
        """Retrieve full workflow definition from template registry."""
        url = f"https://api.n8n.io/api/templates/workflows/{template_id}"
        try:
            resp = await self.client.get(url, timeout=10.0)
            resp.raise_for_status()
            return TemplateDetailDTO.model_validate(resp.json())
        except Exception as exc:
            logger.warning(f"Could not fetch template {template_id}: {exc}")
            return None

    # =========================================================================
    # SYSTEM METADATA & HEALTH
    # =========================================================================

    async def health_check(self) -> Dict[str, Any]:
        """Audits n8n instance reachability, latency, and status."""
        try:
            resp = await self._request("GET", "workflows", params={"limit": 1})
            return {
                "status": "healthy",
                "n8n_host": self.config.n8n_host,
                "api_connected": True,
                "authenticated": bool(self.config.n8n_api_key),
            }
        except Exception as exc:
            return {
                "status": "unhealthy",
                "n8n_host": self.config.n8n_host,
                "error": str(exc),
                "api_connected": False,
            }

    async def get_credentials(self) -> List[Dict[str, Any]]:
        """List configured credential schemas with sensitive secrets protected."""
        try:
            resp = await self._request("GET", "credentials/schema")
            return resp.json() if isinstance(resp.json(), list) else resp.json().get("data", [])
        except Exception:
            return []

    async def get_tags(self) -> List[Dict[str, Any]]:
        """List organizational workflow tags."""
        try:
            resp = await self._request("GET", "tags")
            return resp.json().get("data", []) if isinstance(resp.json(), dict) else resp.json()
        except Exception:
            return []

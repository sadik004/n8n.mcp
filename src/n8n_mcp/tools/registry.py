"""
Central Tool Registry for n8n MCP Server.
Exposes 26 production-grade tools with typed schemas, input validation, and FastMCP registration.
"""

from __future__ import annotations
import inspect
import json
import logging
from typing import Any, Callable, Dict, List, Optional

from n8n_mcp.config import N8nConfig
from n8n_mcp.engine.client import N8nClient
from n8n_mcp.engine.patcher import WorkflowPatcher
from n8n_mcp.engine.snapshots import SnapshotManager
from n8n_mcp.engine.pindata import PinDataManager
from n8n_mcp.engine.node_catalog import NodeCatalogEngine
from n8n_mcp.engine.validator import WorkflowValidator
from n8n_mcp.engine.diagnostics import ExecutionDiagnosticsEngine
from n8n_mcp.engine.healer import AutonomousSelfHealer
from n8n_mcp.engine.stealth_bridge import StealthScraperBridge
from n8n_mcp.models.node import NodePatchRequest

logger = logging.getLogger("n8n_mcp.registry")


class ToolRegistry:
    """Manages MCP tool definitions, JSON Schema generation, and dispatch routing."""

    def __init__(
        self,
        client: Optional[N8nClient] = None,
        config: Optional[N8nConfig] = None,
        snapshot_manager: Optional[SnapshotManager] = None,
    ):
        self.config = config or N8nConfig()
        self.client = client or N8nClient(config=self.config)
        self.snapshot_manager = snapshot_manager or SnapshotManager(snapshots_dir=self.config.snapshots_dir)
        self.patcher = WorkflowPatcher(client=self.client, snapshot_manager=self.snapshot_manager)
        self.pindata_manager = PinDataManager(client=self.client)
        self.catalog_engine = NodeCatalogEngine()
        self.validator = WorkflowValidator()
        self.diagnostics = ExecutionDiagnosticsEngine()
        self.healer = AutonomousSelfHealer(
            client=self.client,
            patcher=self.patcher,
            diagnostics=self.diagnostics,
            max_attempts=2,
        )
        self.stealth_bridge = StealthScraperBridge(config=self.config)

        self._tools: Dict[str, Dict[str, Any]] = {}
        self._dispatch_map: Dict[str, Callable] = {}
        self._register_tools()

    def _register_tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable,
    ):
        self._tools[name] = {
            "name": name,
            "description": description,
            "inputSchema": parameters,
        }
        self._dispatch_map[name] = handler

    def get_tools_manifest(self) -> List[Dict[str, Any]]:
        """Returns MCP-compliant tools manifest list."""
        return list(self._tools.values())

    async def dispatch(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Asynchronously dispatches an incoming tool call to its handler."""
        if tool_name not in self._dispatch_map:
            raise ValueError(f"Unknown tool '{tool_name}'. Available: {list(self._dispatch_map.keys())}")

        handler = self._dispatch_map[tool_name]
        res = handler(**arguments)
        if inspect.isawaitable(res):
            res = await res
        return res

    def register_all_tools(self, mcp: Any) -> None:
        """Registers all tools with an official FastMCP instance."""
        for name, meta in self._tools.items():
            handler = self._dispatch_map[name]
            # Wrap in tool registration
            mcp.tool(name=name, description=meta["description"])(handler)

    def _register_tools(self):
        # 1. n8n_list_workflows
        self._register_tool(
            name="n8n_list_workflows",
            description="Lists all workflows in n8n with optional active status filter, tags, and pagination.",
            parameters={
                "type": "object",
                "properties": {
                    "active": {"type": "boolean", "description": "Filter by active state"},
                    "tags": {"type": "string", "description": "Filter by comma-separated tags"},
                    "limit": {"type": "integer", "default": 100, "description": "Max items to return"},
                    "cursor": {"type": "string", "description": "Pagination cursor"},
                },
            },
            handler=lambda active=None, tags=None, limit=100, cursor=None: self.client.list_workflows(
                active=active, tags=tags, limit=limit, cursor=cursor
            ),
        )

        # 2. n8n_get_workflow
        self._register_tool(
            name="n8n_get_workflow",
            description="Fetches full workflow JSON definition (nodes, connections, settings, pinData).",
            parameters={
                "type": "object",
                "required": ["workflow_id"],
                "properties": {
                    "workflow_id": {"type": "string", "description": "The workflow ID to retrieve"},
                },
            },
            handler=lambda workflow_id: self.client.get_workflow(workflow_id),
        )

        # 3. n8n_create_workflow
        self._register_tool(
            name="n8n_create_workflow",
            description="Creates a new workflow in n8n from structured specification (auto-sanitized payload).",
            parameters={
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "description": "Workflow name"},
                    "nodes": {"type": "array", "items": {"type": "object"}, "description": "Node list"},
                    "connections": {"type": "object", "description": "Connections graph"},
                    "settings": {"type": "object", "description": "Workflow settings"},
                },
            },
            handler=lambda name, nodes=None, connections=None, settings=None: self.client.create_workflow(
                {"name": name, "nodes": nodes or [], "connections": connections or {}, "settings": settings or {}}
            ),
        )

        # 4. n8n_update_workflow
        self._register_tool(
            name="n8n_update_workflow",
            description="Replaces full workflow definition with sanitized payload, stripping read-only fields to prevent HTTP 400 errors.",
            parameters={
                "type": "object",
                "required": ["workflow_id"],
                "properties": {
                    "workflow_id": {"type": "string", "description": "The workflow ID to update"},
                    "name": {"type": "string", "description": "Workflow name"},
                    "nodes": {"type": "array", "items": {"type": "object"}, "description": "Updated nodes"},
                    "connections": {"type": "object", "description": "Updated connections"},
                    "settings": {"type": "object", "description": "Updated settings"},
                },
            },
            handler=lambda workflow_id, name=None, nodes=None, connections=None, settings=None: self.client.update_workflow(
                workflow_id,
                {"name": name, "nodes": nodes or [], "connections": connections or {}, "settings": settings or {}},
            ),
        )

        # 5. n8n_patch_node
        self._register_tool(
            name="n8n_patch_node",
            description="Diff-based partial node updater. Patches specific node parameters/position in-memory; saves 85-90% LLM tokens with auto-snapshot.",
            parameters={
                "type": "object",
                "required": ["workflow_id", "node_name"],
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "node_name": {"type": "string", "description": "Target node name to patch"},
                    "parameters": {"type": "object", "description": "Dictionary of parameters to deep-merge"},
                    "position": {"type": "array", "items": {"type": "number"}, "description": "Updated [x, y] coordinates"},
                    "disabled": {"type": "boolean", "description": "Whether the node is disabled"},
                },
            },
            handler=lambda workflow_id, node_name, parameters=None, position=None, disabled=None: self.patcher.patch_node(
                workflow_id,
                NodePatchRequest(
                    node_name=node_name,
                    parameters=parameters,
                    position=position,
                    disabled=disabled,
                ),
            ),
        )

        # 6. n8n_rollback_workflow
        self._register_tool(
            name="n8n_rollback_workflow",
            description="1-click rollback: restores the previous workflow snapshot if a patch or refactor causes issues.",
            parameters={
                "type": "object",
                "required": ["workflow_id"],
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID to rollback"},
                    "target_version_hash": {"type": "string", "description": "Specific snapshot hash to restore"},
                },
            },
            handler=lambda workflow_id, target_version_hash=None: self.snapshot_manager.rollback_workflow(
                workflow_id, self.client, target_version_hash=target_version_hash
            ),
        )

        # 7. n8n_activate_workflow
        self._register_tool(
            name="n8n_activate_workflow",
            description="Toggles workflow active state (activate / deactivate).",
            parameters={
                "type": "object",
                "required": ["workflow_id"],
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "active": {"type": "boolean", "default": True, "description": "True to activate, False to deactivate"},
                },
            },
            handler=lambda workflow_id, active=True: self.client.activate_workflow(workflow_id, active=active),
        )

        # 8. n8n_delete_workflow
        self._register_tool(
            name="n8n_delete_workflow",
            description="Permanently deletes a workflow by ID.",
            parameters={
                "type": "object",
                "required": ["workflow_id"],
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID to delete"},
                },
            },
            handler=lambda workflow_id: self.client.delete_workflow(workflow_id),
        )

        # 9. n8n_search_nodes
        self._register_tool(
            name="n8n_search_nodes",
            description="Anti-hallucination node search. Search n8n node types, descriptions, and categories with 0ms latency.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "default": "", "description": "Search keyword or category"},
                },
            },
            handler=lambda query="": [n.model_dump() for n in self.catalog_engine.search_nodes(query)],
        )

        # 10. n8n_get_node_schema
        self._register_tool(
            name="n8n_get_node_schema",
            description="Parameter contract inspector: returns exact properties, enums, and operations for any n8n node.",
            parameters={
                "type": "object",
                "required": ["node_name_or_alias"],
                "properties": {
                    "node_name_or_alias": {"type": "string", "description": "Full node type name or friendly alias"},
                },
            },
            handler=lambda node_name_or_alias: self.catalog_engine.get_node_schema(node_name_or_alias).model_dump(),
        )

        # 11. n8n_validate_workflow
        self._register_tool(
            name="n8n_validate_workflow",
            description="DAG cycle detection, dangling nodes check, expression syntax linter, and Code node Python AST check.",
            parameters={
                "type": "object",
                "required": ["workflow"],
                "properties": {
                    "workflow": {"type": "object", "description": "Workflow JSON specification"},
                },
            },
            handler=lambda workflow: self.validator.validate_workflow(workflow).model_dump(),
        )

        # 12. n8n_validate_ai_agent_graph
        self._register_tool(
            name="n8n_validate_ai_agent_graph",
            description="LangChain AI Agent Validation: enforces required ai_languageModel, ai_tool, and ai_memory sub-node ports.",
            parameters={
                "type": "object",
                "required": ["workflow"],
                "properties": {
                    "workflow": {"type": "object", "description": "Workflow JSON specification"},
                },
            },
            handler=lambda workflow: self.validator.validate_ai_agent_graph(workflow).model_dump(),
        )

        # 13. n8n_set_pinned_data
        self._register_tool(
            name="n8n_set_pinned_data",
            description="Safe Sandbox Testing: injects mock test data into trigger nodes (pinData) without side-effects.",
            parameters={
                "type": "object",
                "required": ["workflow_id", "node_name", "data"],
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "node_name": {"type": "string", "description": "Target node name to receive pinned data"},
                    "data": {"description": "Dictionary or list of items to inject as pinData"},
                },
            },
            handler=lambda workflow_id, node_name, data: self.pindata_manager.set_pinned_data(
                workflow_id, node_name, data
            ),
        )

        # 14. n8n_clear_pinned_data
        self._register_tool(
            name="n8n_clear_pinned_data",
            description="Clears pinned data from specific or all nodes before pushing to live production.",
            parameters={
                "type": "object",
                "required": ["workflow_id"],
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "node_name": {"type": "string", "description": "Optional specific node name to clear"},
                },
            },
            handler=lambda workflow_id, node_name=None: self.pindata_manager.clear_pinned_data(
                workflow_id, node_name=node_name
            ),
        )

        # 15. n8n_list_executions
        self._register_tool(
            name="n8n_list_executions",
            description="Queries execution history with filters (workflowId, status: success, error, waiting).",
            parameters={
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Filter by workflow ID"},
                    "status": {"type": "string", "description": "Filter by status: success, error, waiting"},
                    "limit": {"type": "integer", "default": 20, "description": "Max executions to return"},
                    "cursor": {"type": "string", "description": "Pagination cursor"},
                },
            },
            handler=lambda workflow_id=None, status=None, limit=20, cursor=None: self.client.list_executions(
                workflow_id=workflow_id, status=status, limit=limit, cursor=cursor
            ),
        )

        # 16. n8n_get_execution
        self._register_tool(
            name="n8n_get_execution",
            description="Inspects full execution data, node-by-node runtime, and I/O records.",
            parameters={
                "type": "object",
                "required": ["execution_id"],
                "properties": {
                    "execution_id": {"type": "string", "description": "Execution ID"},
                    "include_data": {"type": "boolean", "default": True, "description": "Include node execution data"},
                },
            },
            handler=lambda execution_id, include_data=True: self.client.get_execution(
                execution_id, include_data=include_data
            ),
        )

        # 17. n8n_audit_errors
        self._register_tool(
            name="n8n_audit_errors",
            description="Diagnoses failed executions, pinpoints crashed nodes, and generates structured Root Cause Analysis (RCA).",
            parameters={
                "type": "object",
                "required": ["execution_id"],
                "properties": {
                    "execution_id": {"type": "string", "description": "Failed execution ID to diagnose"},
                },
            },
            handler=lambda execution_id: self._handle_audit_errors(execution_id),
        )

        # 18. n8n_retry_execution
        self._register_tool(
            name="n8n_retry_execution",
            description="Retries a failed workflow execution by execution ID.",
            parameters={
                "type": "object",
                "required": ["execution_id"],
                "properties": {
                    "execution_id": {"type": "string", "description": "Execution ID to retry"},
                    "load_workflow": {"type": "boolean", "default": True, "description": "Reload latest workflow definition"},
                },
            },
            handler=lambda execution_id, load_workflow=True: self.client.retry_execution(
                execution_id, load_workflow=load_workflow
            ),
        )

        # 19. n8n_delete_execution
        self._register_tool(
            name="n8n_delete_execution",
            description="Removes execution records from history.",
            parameters={
                "type": "object",
                "required": ["execution_id"],
                "properties": {
                    "execution_id": {"type": "string", "description": "Execution ID to remove"},
                },
            },
            handler=lambda execution_id: self.client.delete_execution(execution_id),
        )

        # 20. n8n_auto_heal_execution
        self._register_tool(
            name="n8n_auto_heal_execution",
            description="Autonomous self-healing loop: Inspects failure -> diagnoses RCA -> patches node -> retries execution (max 2 attempts).",
            parameters={
                "type": "object",
                "required": ["execution_id", "repair_parameters"],
                "properties": {
                    "execution_id": {"type": "string", "description": "Failed execution ID"},
                    "repair_parameters": {"type": "object", "description": "Parameters to patch on the crashed node"},
                    "target_node_name": {"type": "string", "description": "Optional specific node name to patch"},
                },
            },
            handler=lambda execution_id, repair_parameters, target_node_name=None: self.healer.heal_execution(
                execution_id=execution_id,
                repair_parameters=repair_parameters,
                target_node_name=target_node_name,
            ),
        )

        # 21. n8n_search_templates
        self._register_tool(
            name="n8n_search_templates",
            description="Searches n8n's 2000+ verified official & community template library by keyword or category.",
            parameters={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "Search keyword or use case"},
                    "page": {"type": "integer", "default": 1, "description": "Page number"},
                    "limit": {"type": "integer", "default": 20, "description": "Results per page"},
                },
            },
            handler=lambda query, page=1, limit=20: self.client.search_templates(query=query, page=page, limit=limit),
        )

        # 22. n8n_get_template
        self._register_tool(
            name="n8n_get_template",
            description="Downloads full workflow template JSON ready for deployment.",
            parameters={
                "type": "object",
                "required": ["template_id"],
                "properties": {
                    "template_id": {"description": "Template ID to fetch"},
                },
            },
            handler=lambda template_id: self.client.get_template(template_id),
        )

        # 23. n8n_create_stealth_scraper_node
        self._register_tool(
            name="n8n_create_stealth_scraper_node",
            description="behavioral-playwright bridge: generates pre-configured node to bypass Cloudflare/Turnstile and scrape protected sites.",
            parameters={
                "type": "object",
                "required": ["node_name", "target_url"],
                "properties": {
                    "node_name": {"type": "string", "description": "Name for the scraper node"},
                    "target_url": {"type": "string", "description": "Target website URL to scrape"},
                    "selector": {"type": "string", "description": "CSS selector to wait for"},
                    "position": {"type": "array", "items": {"type": "number"}, "description": "Canvas position coordinates"},
                },
            },
            handler=lambda node_name, target_url, selector=None, position=None: self.stealth_bridge.create_stealth_node(
                node_name=node_name,
                target_url=target_url,
                selector=selector,
                position=position,
            ),
        )

        # 24. n8n_trigger_webhook
        self._register_tool(
            name="n8n_trigger_webhook",
            description="Executes test or production webhooks with custom payload, method, and query params.",
            parameters={
                "type": "object",
                "required": ["path"],
                "properties": {
                    "path": {"type": "string", "description": "Webhook endpoint path"},
                    "is_test": {"type": "boolean", "default": True, "description": "True for /webhook-test/, False for /webhook/"},
                    "method": {"type": "string", "default": "POST", "description": "HTTP method"},
                    "payload": {"type": "object", "description": "JSON request body"},
                    "headers": {"type": "object", "description": "HTTP request headers"},
                },
            },
            handler=lambda path, is_test=True, method="POST", payload=None, headers=None: self.client.trigger_webhook(
                path=path,
                is_test=is_test,
                method=method,
                payload=payload,
                headers=headers,
            ),
        )

        # 25. n8n_health_check
        self._register_tool(
            name="n8n_health_check",
            description="Checks n8n instance version, public API reachability, and response latency.",
            parameters={"type": "object", "properties": {}},
            handler=lambda: self.client.health_check(),
        )

        # 26. n8n_list_credentials
        self._register_tool(
            name="n8n_list_credentials",
            description="Lists available credential IDs and types with sensitive secrets masked.",
            parameters={"type": "object", "properties": {}},
            handler=lambda: self.client.get_credentials(),
        )

    async def _handle_audit_errors(self, execution_id: str) -> Dict[str, Any]:
        """Internal handler for error auditing and RCA."""
        exec_detail = await self.client.get_execution(execution_id, include_data=True)
        report = self.diagnostics.diagnose_execution(exec_detail)
        return report.model_dump()

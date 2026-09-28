"""
Unit tests for ToolRegistry exposing all 26 production MCP tools.
Testing tool manifest catalog, parameter schema reflection, and async dispatch routing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from n8n_mcp.tools.registry import ToolRegistry
from n8n_mcp.models.workflow import WorkflowDTO
from n8n_mcp.models.diagnostics import DiagnosticsReportDTO


@pytest.fixture
def mock_registry():
    client = AsyncMock()
    sample_wf = WorkflowDTO(id="wf-1", name="Test Flow", nodes=[], connections={})
    client.list_workflows = AsyncMock(return_value=MagicMock(data=[sample_wf]))
    client.get_workflow = AsyncMock(return_value=sample_wf)
    client.health_check = AsyncMock(return_value={"status": "healthy"})

    registry = ToolRegistry(client=client)
    return registry


def test_tool_registry_contains_26_tools(mock_registry):
    """Verify exactly 26 production MCP tools are defined and registered."""
    tools = mock_registry.get_tools_manifest()
    assert len(tools) == 26

    expected_tool_names = [
        "n8n_list_workflows",
        "n8n_get_workflow",
        "n8n_create_workflow",
        "n8n_update_workflow",
        "n8n_patch_node",
        "n8n_rollback_workflow",
        "n8n_activate_workflow",
        "n8n_delete_workflow",
        "n8n_search_nodes",
        "n8n_get_node_schema",
        "n8n_validate_workflow",
        "n8n_validate_ai_agent_graph",
        "n8n_set_pinned_data",
        "n8n_clear_pinned_data",
        "n8n_list_executions",
        "n8n_get_execution",
        "n8n_audit_errors",
        "n8n_retry_execution",
        "n8n_delete_execution",
        "n8n_auto_heal_execution",
        "n8n_search_templates",
        "n8n_get_template",
        "n8n_create_stealth_scraper_node",
        "n8n_trigger_webhook",
        "n8n_health_check",
        "n8n_list_credentials",
    ]

    registered_names = [t["name"] for t in tools]
    for expected in expected_tool_names:
        assert expected in registered_names, f"Tool '{expected}' is missing from registry!"


@pytest.mark.asyncio
async def test_dispatch_health_check(mock_registry):
    """Verify dispatching n8n_health_check tool."""
    res = await mock_registry.dispatch("n8n_health_check", {})
    assert res["status"] == "healthy"


@pytest.mark.asyncio
async def test_dispatch_search_nodes(mock_registry):
    """Verify dispatching n8n_search_nodes tool."""
    res = await mock_registry.dispatch("n8n_search_nodes", {"query": "slack"})
    assert isinstance(res, list)
    assert any(n.get("name") == "n8n-nodes-base.slack" for n in res)


@pytest.mark.asyncio
async def test_dispatch_unknown_tool_raises(mock_registry):
    """Verify dispatching an unregistered tool raises ValueError."""
    with pytest.raises(ValueError, match="Unknown tool 'n8n_non_existent'"):
        await mock_registry.dispatch("n8n_non_existent", {})

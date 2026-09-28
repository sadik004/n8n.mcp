"""
End-to-end integration tests for n8n MCP Server.
Verifies FastMCP registration, JSON-RPC 2.0 handshake, tool discovery, and tool execution.
"""

from __future__ import annotations
import json
import pytest
from unittest.mock import AsyncMock, patch

from n8n_mcp.server import N8nMcpServer, create_mcp_server
from n8n_mcp.config import N8nConfig


@pytest.fixture
def test_config(tmp_path):
    return N8nConfig(
        n8n_base_url="http://localhost:5678",
        n8n_api_key="test-api-key",
        snapshots_dir=tmp_path / "snapshots",
    )


@pytest.fixture
def mcp_server(test_config):
    return N8nMcpServer(config=test_config)


@pytest.mark.asyncio
async def test_fastmcp_initialization_and_tool_count(test_config):
    """Verifies that create_mcp_server correctly binds all 26 MCP tools to FastMCP."""
    fast_mcp = create_mcp_server(config=test_config)
    tools = await fast_mcp.list_tools()
    assert len(tools) == 26
    tool_names = [t.name for t in tools]
    assert "n8n_list_workflows" in tool_names
    assert "n8n_patch_node" in tool_names
    assert "n8n_validate_workflow" in tool_names
    assert "n8n_auto_heal_execution" in tool_names
    assert "n8n_create_stealth_scraper_node" in tool_names


@pytest.mark.asyncio
async def test_jsonrpc_initialize_handshake(mcp_server):
    """Verifies JSON-RPC 2.0 initialize request handshake."""
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }
    resp = await mcp_server.handle_request(req)
    assert resp is not None
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "n8n-mcp"
    assert resp["result"]["serverInfo"]["version"] == "0.1.0"
    assert "tools" in resp["result"]["capabilities"]


@pytest.mark.asyncio
async def test_jsonrpc_notifications_and_ping(mcp_server):
    """Verifies notifications return None and ping returns empty object."""
    notif = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
    }
    resp = await mcp_server.handle_request(notif)
    assert resp is None

    ping = {
        "jsonrpc": "2.0",
        "id": 42,
        "method": "ping",
    }
    resp = await mcp_server.handle_request(ping)
    assert resp == {"jsonrpc": "2.0", "id": 42, "result": {}}


@pytest.mark.asyncio
async def test_jsonrpc_unknown_method(mcp_server):
    """Verifies unknown methods return JSON-RPC -32601 error."""
    req = {
        "jsonrpc": "2.0",
        "id": 99,
        "method": "non_existent_method",
        "params": {},
    }
    resp = await mcp_server.handle_request(req)
    assert resp["error"]["code"] == -32601
    assert "Method 'non_existent_method' not found" in resp["error"]["message"]


@pytest.mark.asyncio
async def test_jsonrpc_tools_list_discovery(mcp_server):
    """Verifies tools/list returns complete 26-tool catalog with schema manifests."""
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
    }
    resp = await mcp_server.handle_request(req)
    tools = resp["result"]["tools"]
    assert len(tools) == 26
    names = {t["name"] for t in tools}
    expected_core_tools = {
        "n8n_list_workflows",
        "n8n_get_workflow",
        "n8n_create_workflow",
        "n8n_update_workflow",
        "n8n_patch_node",
        "n8n_rollback_workflow",
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
        "n8n_auto_heal_execution",
        "n8n_search_templates",
        "n8n_get_template",
        "n8n_create_stealth_scraper_node",
        "n8n_trigger_webhook",
        "n8n_health_check",
        "n8n_list_credentials",
    }
    assert expected_core_tools.issubset(names)


@pytest.mark.asyncio
async def test_jsonrpc_call_search_nodes(mcp_server):
    """Verifies executing tools/call on n8n_search_nodes."""
    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "n8n_search_nodes",
            "arguments": {"query": "webhook"},
        },
    }
    resp = await mcp_server.handle_request(req)
    assert "result" in resp
    content = resp["result"]["content"][0]["text"]
    data = json.loads(content)
    assert any(item["name"] == "n8n-nodes-base.webhook" for item in data)


@pytest.mark.asyncio
async def test_jsonrpc_call_validate_workflow(mcp_server):
    """Verifies executing tools/call on n8n_validate_workflow."""
    workflow = {
        "name": "Test DAG",
        "nodes": [
            {"id": "1", "name": "Start", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1, "position": [100, 200]},
            {"id": "2", "name": "Code", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [300, 200]},
        ],
        "connections": {
            "Start": {"main": [[{"node": "Code", "type": "main", "index": 0}]]}
        },
    }
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "n8n_validate_workflow",
            "arguments": {"workflow": workflow},
        },
    }
    resp = await mcp_server.handle_request(req)
    content = json.loads(resp["result"]["content"][0]["text"])
    assert content["is_valid"] is True
    assert content["cycle_detected"] is False


@pytest.mark.asyncio
async def test_jsonrpc_call_create_stealth_scraper_node(mcp_server):
    """Verifies executing tools/call on n8n_create_stealth_scraper_node."""
    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "n8n_create_stealth_scraper_node",
            "arguments": {
                "node_name": "RedditScraper",
                "target_url": "https://reddit.com/r/programming",
                "selector": "shreddit-post",
                "position": [250, 450],
            },
        },
    }
    resp = await mcp_server.handle_request(req)
    content = json.loads(resp["result"]["content"][0]["text"])
    assert content["name"] == "RedditScraper"
    assert content["type"] == "n8n-nodes-base.httpRequest"
    assert content["parameters"]["method"] == "POST"
    body = json.loads(content["parameters"]["jsonBody"])
    assert body["url"] == "https://reddit.com/r/programming"
    assert body["stealth_mode"] is True


@pytest.mark.asyncio
async def test_jsonrpc_call_tool_error_handling(mcp_server):
    """Verifies proper error handling when a tool throws an exception."""
    req = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "n8n_get_node_schema",
            "arguments": {"node_name_or_alias": "non_existent_fake_node_123"},
        },
    }
    resp = await mcp_server.handle_request(req)
    assert resp["result"]["isError"] is True
    assert "Node schema not found for 'non_existent_fake_node_123'" in resp["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_fastmcp_direct_tool_invocation(mcp_server):
    """Verifies direct tool calling through FastMCP interface."""
    res = await mcp_server.mcp.call_tool("n8n_search_nodes", {"query": "postgres"})
    assert len(res) == 1
    assert "n8n-nodes-base.postgres" in res[0].text

"""
Unit tests for PinDataManager safe sandbox testing engine.
Testing smart wrapping ([{"json": ...}]), node name mapping, and clearing operations.
"""

import pytest
from unittest.mock import AsyncMock
from n8n_mcp.engine.pindata import PinDataManager
from n8n_mcp.models.workflow import WorkflowDTO
from n8n_mcp.models.node import NodeDTO


@pytest.fixture
def mock_client():
    client = AsyncMock()
    workflow = WorkflowDTO(
        id="wf-pin-99",
        name="Billing Processor",
        nodes=[
            NodeDTO(name="Stripe Webhook", type="n8n-nodes-base.webhook", parameters={}),
            NodeDTO(name="Discord Alert", type="n8n-nodes-base.discord", parameters={}),
        ],
        connections={},
        settings={},
        pinData={"Stripe Webhook": [{"json": {"existing": True}}]},
    )
    client.get_workflow = AsyncMock(return_value=workflow)
    client.update_workflow = AsyncMock(return_value=workflow)
    return client


@pytest.mark.asyncio
async def test_set_pinned_data_smart_wrapping(mock_client):
    """Verify raw dictionaries are wrapped cleanly into [{'json': {...}}]."""
    manager = PinDataManager(client=mock_client)

    # 1. Test passing a raw dict
    raw_event = {"event": "charge.succeeded", "amount": 5000}
    result = await manager.set_pinned_data("wf-pin-99", "Stripe Webhook", raw_event)

    assert result["node_name"] == "Stripe Webhook"
    assert result["item_count"] == 1

    # Verify update_workflow payload formatting
    mock_client.update_workflow.assert_called_once()
    payload = mock_client.update_workflow.call_args[0][1]
    assert payload["pinData"]["Stripe Webhook"] == [{"json": raw_event}]


@pytest.mark.asyncio
async def test_set_pinned_data_preserves_already_wrapped(mock_client):
    """Verify data already formatted as [{'json': {...}}] is not double-wrapped."""
    manager = PinDataManager(client=mock_client)
    already_wrapped = [{"json": {"item": "data1"}}, {"json": {"item": "data2"}}]

    await manager.set_pinned_data("wf-pin-99", "Stripe Webhook", already_wrapped)

    payload = mock_client.update_workflow.call_args[0][1]
    assert payload["pinData"]["Stripe Webhook"] == already_wrapped


@pytest.mark.asyncio
async def test_clear_pinned_data(mock_client):
    """Verify clearing pinned data for a specific node or entire workflow."""
    manager = PinDataManager(client=mock_client)

    # Clear specific node
    await manager.clear_pinned_data("wf-pin-99", node_name="Stripe Webhook")
    payload = mock_client.update_workflow.call_args[0][1]
    assert "Stripe Webhook" not in payload["pinData"]

    # Clear all nodes
    await manager.clear_pinned_data("wf-pin-99", node_name=None)
    payload_all = mock_client.update_workflow.call_args[0][1]
    assert payload_all["pinData"] == {}

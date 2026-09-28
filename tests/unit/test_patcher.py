"""
Unit tests for WorkflowPatcher engine.
Testing Read-Modify-Write transaction, recursive parameter deep-merge, and token-saving diff generation.
"""

import pytest
from unittest.mock import AsyncMock
from n8n_mcp.engine.patcher import WorkflowPatcher
from n8n_mcp.engine.snapshots import SnapshotManager
from n8n_mcp.models.workflow import WorkflowDTO
from n8n_mcp.models.node import NodeDTO, NodePatchRequest


@pytest.fixture
def mock_client():
    client = AsyncMock()
    sample_workflow = WorkflowDTO(
        id="wf-patch-1",
        name="Automation Pipeline",
        active=True,
        nodes=[
            NodeDTO(
                id="n1",
                name="Slack Alert",
                type="n8n-nodes-base.slack",
                typeVersion=2,
                position=[100, 200],
                parameters={
                    "channel": "#general",
                    "text": "Hello world",
                    "options": {"sendAsUser": True, "mrkdwn": True},
                },
                disabled=False,
            ),
            NodeDTO(
                id="n2",
                name="Postgres Logger",
                type="n8n-nodes-base.postgres",
                typeVersion=1,
                position=[300, 200],
                parameters={"operation": "insert", "table": "logs"},
                disabled=False,
            ),
        ],
        connections={},
        settings={"executionOrder": "v1"},
    )
    client.get_workflow = AsyncMock(return_value=sample_workflow)
    client.update_workflow = AsyncMock(return_value=sample_workflow)
    return client


@pytest.fixture
def snapshot_manager(tmp_path):
    return SnapshotManager(snapshots_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_deep_merge_node_parameters(mock_client, snapshot_manager):
    """Verify deep-merge updates only targeted nested keys without wiping sibling settings."""
    patcher = WorkflowPatcher(client=mock_client, snapshot_manager=snapshot_manager)

    patch_req = NodePatchRequest(
        node_name="Slack Alert",
        parameters={
            "text": "Critical Incident Detected!",
            "options": {"mrkdwn": False},  # sendAsUser=True must be preserved!
        },
    )

    result = await patcher.patch_node("wf-patch-1", patch_req)

    assert result["workflow_id"] == "wf-patch-1"
    assert result["node_name"] == "Slack Alert"
    assert "updated_parameters" in result

    # Check update_workflow was called with preserved sibling options
    mock_client.update_workflow.assert_called_once()
    saved_payload = mock_client.update_workflow.call_args[0][1]

    slack_node = next(n for n in saved_payload["nodes"] if n["name"] == "Slack Alert")
    assert slack_node["parameters"]["text"] == "Critical Incident Detected!"
    assert slack_node["parameters"]["channel"] == "#general"  # preserved
    assert slack_node["parameters"]["options"]["mrkdwn"] is False  # updated
    assert slack_node["parameters"]["options"]["sendAsUser"] is True  # preserved!


@pytest.mark.asyncio
async def test_patcher_raises_for_missing_node(mock_client, snapshot_manager):
    """Verify ValueError is raised if target node name does not exist in workflow."""
    patcher = WorkflowPatcher(client=mock_client, snapshot_manager=snapshot_manager)
    patch_req = NodePatchRequest(node_name="NonExistentNode", parameters={"k": "v"})

    with pytest.raises(ValueError, match="Node 'NonExistentNode' not found"):
        await patcher.patch_node("wf-patch-1", patch_req)

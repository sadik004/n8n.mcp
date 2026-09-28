"""
Unit tests for SnapshotManager and 1-click rollback engine.
Testing directory safety, JSON persistence, and workflow state restoration.
"""

import pytest
from unittest.mock import AsyncMock
from n8n_mcp.engine.snapshots import SnapshotManager
from n8n_mcp.models.workflow import WorkflowDTO
from n8n_mcp.models.node import NodeDTO


@pytest.fixture
def sample_workflow():
    return WorkflowDTO(
        id="wf-snap-10",
        name="Stateful Pipeline",
        nodes=[
            NodeDTO(name="Trigger", type="n8n-nodes-base.webhook", parameters={"path": "lead"})
        ],
        connections={},
        settings={},
    )


@pytest.mark.asyncio
async def test_create_and_restore_snapshot(tmp_path, sample_workflow):
    """Verify creating a snapshot and rolling back restores exact workflow state."""
    manager = SnapshotManager(snapshots_dir=str(tmp_path))

    # 1. Create Snapshot
    snap = await manager.create_snapshot(sample_workflow)
    assert snap.workflow_id == "wf-snap-10"
    assert snap.version_hash != ""

    # Verify JSON file written to disk
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    assert "wf-snap-10" in files[0].name

    # 2. Rollback with mock client
    mock_client = AsyncMock()
    mock_client.update_workflow = AsyncMock(return_value=sample_workflow)

    result = await manager.rollback_workflow("wf-snap-10", client=mock_client)
    assert result.status == "restored"
    assert result.workflow_id == "wf-snap-10"
    assert result.restored_version_hash == snap.version_hash

    # Verify client update was executed with original snapshot data
    mock_client.update_workflow.assert_called_once()
    called_payload = mock_client.update_workflow.call_args[0][1]
    assert called_payload["name"] == "Stateful Pipeline"


@pytest.mark.asyncio
async def test_rollback_raises_when_no_snapshot(tmp_path):
    """Verify ValueError is raised when rolling back a workflow with no snapshots."""
    manager = SnapshotManager(snapshots_dir=str(tmp_path))
    mock_client = AsyncMock()

    with pytest.raises(ValueError, match="No snapshot found for workflow"):
        await manager.rollback_workflow("wf-no-snapshot", client=mock_client)

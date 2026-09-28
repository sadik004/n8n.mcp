"""
Unit tests for AutonomousSelfHealer engine.
Testing bounded retry loop (max_attempts=2), automated patch invocation, and recovery reporting.
"""

import pytest
from unittest.mock import AsyncMock
from n8n_mcp.engine.healer import AutonomousSelfHealer
from n8n_mcp.engine.diagnostics import ExecutionDiagnosticsEngine
from n8n_mcp.models.diagnostics import SelfHealingReportDTO
from n8n_mcp.models.execution import ExecutionDetailDTO


@pytest.fixture
def mock_client():
    client = AsyncMock()
    # 1. First execution is failed
    failed_exec = ExecutionDetailDTO(
        id="exec-fail-1",
        workflow_id="wf-healer",
        status="error",
        finished=True,
        data={
            "resultData": {
                "error": {
                    "message": "Invalid URL in request",
                    "node": {"name": "Webhook Call"},
                }
            }
        },
    )
    # 2. Retried execution succeeds
    retried_exec = ExecutionDetailDTO(
        id="exec-healed-2",
        workflow_id="wf-healer",
        status="success",
        finished=True,
        data={},
    )

    client.get_execution = AsyncMock(side_effect=[failed_exec, retried_exec])
    client.retry_execution = AsyncMock(return_value={"id": "exec-healed-2", "status": "running"})
    return client


@pytest.fixture
def mock_patcher():
    patcher = AsyncMock()
    patcher.patch_node = AsyncMock(return_value={"status": "patched", "node_name": "Webhook Call"})
    return patcher


@pytest.mark.asyncio
async def test_auto_heal_successful_recovery(mock_client, mock_patcher):
    """Verify autonomous loop diagnoses failure, applies patch, retries, and confirms recovery."""
    diagnostics = ExecutionDiagnosticsEngine()
    healer = AutonomousSelfHealer(
        client=mock_client,
        patcher=mock_patcher,
        diagnostics=diagnostics,
        max_attempts=2,
    )

    repair_params = {"url": "https://api.fixed-endpoint.com/webhook"}
    report = await healer.heal_execution(
        execution_id="exec-fail-1",
        repair_parameters=repair_params,
    )

    assert isinstance(report, SelfHealingReportDTO)
    assert report.success is True
    assert report.execution_id == "exec-fail-1"
    assert report.new_execution_id == "exec-healed-2"
    assert report.patched_node == "Webhook Call"
    assert report.status == "healed"

    # Verify patcher was called
    mock_patcher.patch_node.assert_called_once()
    # Verify retry was executed
    mock_client.retry_execution.assert_called_once_with("exec-fail-1")


@pytest.mark.asyncio
async def test_auto_heal_bounded_attempts_failure(mock_patcher):
    """Verify loop strictly terminates and does not loop forever when retried execution still fails."""
    client = AsyncMock()
    persistent_fail_exec = ExecutionDetailDTO(
        id="exec-fail-loop",
        workflow_id="wf-broken",
        status="error",
        finished=True,
        data={
            "resultData": {
                "error": {
                    "message": "Persistent 500 internal server error",
                    "node": {"name": "Flaky Node"},
                }
            }
        },
    )
    # Repeated failures
    client.get_execution = AsyncMock(return_value=persistent_fail_exec)
    client.retry_execution = AsyncMock(return_value={"id": "exec-fail-loop-retry"})

    diagnostics = ExecutionDiagnosticsEngine()
    healer = AutonomousSelfHealer(
        client=client,
        patcher=mock_patcher,
        diagnostics=diagnostics,
        max_attempts=2,
    )

    report = await healer.heal_execution(
        execution_id="exec-fail-loop",
        repair_parameters={"retry": 1},
    )

    assert report.success is False
    assert report.attempt <= 2
    assert report.status == "failed"

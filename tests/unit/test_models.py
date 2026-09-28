"""
Unit tests for Pydantic v2 domain models and DTOs in n8n MCP.
Testing serialization, validation, field stripping in WorkflowSanitizedPayload, and N8nBaseModel extra='ignore'.
"""

import pytest
from n8n_mcp.models.base import N8nBaseModel
from n8n_mcp.models.node import NodeDTO, NodePatchRequest, NodeSchemaDTO
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
from n8n_mcp.models.diagnostics import (
    WorkflowValidationResultDTO,
    AIAgentValidationResultDTO,
    DiagnosticsReportDTO,
    SelfHealingReportDTO,
)
from n8n_mcp.models.template import TemplateSummaryDTO, TemplateDetailDTO
from n8n_mcp.models.snapshot import SnapshotDTO, RollbackResultDTO


def test_n8n_base_model_ignores_extra_fields():
    """Verify N8nBaseModel ignores unexpected n8n API fields without crashing."""
    class DummyModel(N8nBaseModel):
        name: str

    obj = DummyModel.model_validate({"name": "Webhook Node", "unexpected_future_field": 42})
    assert obj.name == "Webhook Node"
    assert not hasattr(obj, "unexpected_future_field")


def test_node_dto_serialization():
    """Verify NodeDTO parsing and defaults."""
    raw_node = {
        "id": "node-1",
        "name": "HTTP Request",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [250.0, 300.0],
        "parameters": {"url": "https://api.example.com/v1", "method": "POST"},
    }
    node = NodeDTO.model_validate(raw_node)
    assert node.id == "node-1"
    assert node.name == "HTTP Request"
    assert node.type == "n8n-nodes-base.httpRequest"
    assert node.type_version == 4.2
    assert node.parameters["method"] == "POST"
    assert not node.disabled


def test_workflow_sanitized_payload_strips_read_only_fields():
    """Verify WorkflowSanitizedPayload retains strictly mutable root fields."""
    raw_workflow_from_get = {
        "id": "wf-12345",
        "name": "Order Ingestion Flow",
        "active": True,
        "versionId": "ver-abc-987",
        "createdAt": "2026-09-28T00:00:00.000Z",
        "updatedAt": "2026-09-28T10:00:00.000Z",
        "triggerCount": 5,
        "tags": [{"id": "tag-1", "name": "E-Commerce"}],
        "nodes": [
            {
                "name": "Start",
                "type": "n8n-nodes-base.start",
                "typeVersion": 1,
                "position": [0, 0],
                "parameters": {},
            }
        ],
        "connections": {"Start": {"main": [[{"node": "Next", "type": "main", "index": 0}]]}},
        "settings": {"executionOrder": "v1"},
        "pinData": {"Start": [{"json": {"item": "mock"}}]},
    }

    # WorkflowDTO keeps full details
    full_wf = WorkflowDTO.model_validate(raw_workflow_from_get)
    assert full_wf.id == "wf-12345"
    assert full_wf.trigger_count == 5

    # WorkflowSanitizedPayload encapsulates strictly mutable fields
    sanitized = WorkflowSanitizedPayload.from_workflow(full_wf)
    payload_dict = sanitized.model_dump(by_alias=True, exclude_unset=True)

    # Must include mutable fields
    assert payload_dict["name"] == "Order Ingestion Flow"
    assert len(payload_dict["nodes"]) == 1
    assert "Start" in payload_dict["connections"]
    assert payload_dict["settings"]["executionOrder"] == "v1"
    assert "Start" in payload_dict["pinData"]

    # Must NOT contain read-only fields
    for forbidden_key in ("id", "versionId", "createdAt", "updatedAt", "triggerCount", "tags", "active"):
        assert forbidden_key not in payload_dict


def test_node_patch_request():
    """Verify NodePatchRequest parsing."""
    patch = NodePatchRequest(
        node_name="Slack Notification",
        parameters={"channel": "#alerts", "message": "Payment verified"},
        disabled=False,
    )
    assert patch.node_name == "Slack Notification"
    assert patch.parameters["channel"] == "#alerts"
    assert patch.disabled is False


def test_execution_dto_and_list_response():
    """Verify ExecutionDTO and ExecutionListResponse."""
    raw_exec = {
        "id": "exec-99",
        "finished": True,
        "mode": "webhook",
        "status": "success",
        "startedAt": "2026-09-28T08:00:00.000Z",
        "stoppedAt": "2026-09-28T08:00:02.000Z",
        "workflowId": "wf-12345",
    }
    execution = ExecutionDTO.model_validate(raw_exec)
    assert execution.id == "exec-99"
    assert execution.status == "success"

    resp = ExecutionListResponse(data=[execution], next_cursor="cursor_abc")
    assert len(resp.data) == 1
    assert resp.next_cursor == "cursor_abc"


def test_diagnostics_and_self_healing_models():
    """Verify DiagnosticsReportDTO and SelfHealingReportDTO."""
    diag = DiagnosticsReportDTO(
        execution_id="exec-404",
        workflow_id="wf-12345",
        crashed_node="HTTP Request",
        error_type="HTTP 401 Unauthorized",
        error_message="Invalid credentials supplied in header",
        root_cause_analysis="API key expired or header name was misspelled.",
        remediation_suggestions=["Inspect X-API-KEY header", "Rotate expired credentials"],
    )
    assert diag.crashed_node == "HTTP Request"
    assert len(diag.remediation_suggestions) == 2

    heal = SelfHealingReportDTO(
        execution_id="exec-404",
        workflow_id="wf-12345",
        attempt=1,
        success=True,
        patched_node="HTTP Request",
        new_execution_id="exec-405",
        status="healed",
    )
    assert heal.success is True
    assert heal.new_execution_id == "exec-405"


def test_snapshot_and_rollback_models():
    """Verify SnapshotDTO and RollbackResultDTO."""
    snap = SnapshotDTO(
        workflow_id="wf-100",
        timestamp="2026-09-28T10:00:00Z",
        version_hash="a1b2c3d4e5f6",
        workflow_data={"name": "Test Flow", "nodes": []},
    )
    assert snap.workflow_id == "wf-100"
    assert snap.version_hash == "a1b2c3d4e5f6"

    rollback = RollbackResultDTO(
        workflow_id="wf-100",
        restored_version_hash="a1b2c3d4e5f6",
        timestamp="2026-09-28T10:01:00Z",
    )
    assert rollback.status == "restored"

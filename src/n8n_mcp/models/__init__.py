"""
Domain models and Data Transfer Objects (DTOs) for n8n MCP Server.
"""

from n8n_mcp.models.base import N8nBaseModel
from n8n_mcp.models.node import (
    NodeDTO,
    NodeConnectionItemDTO,
    NodePatchRequest,
    NodeSchemaDTO,
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
from n8n_mcp.models.diagnostics import (
    WorkflowValidationResultDTO,
    AIAgentValidationResultDTO,
    DiagnosticsReportDTO,
    SelfHealingReportDTO,
)
from n8n_mcp.models.template import TemplateSummaryDTO, TemplateDetailDTO
from n8n_mcp.models.snapshot import SnapshotDTO, RollbackResultDTO

__all__ = [
    "N8nBaseModel",
    "NodeDTO",
    "NodeConnectionItemDTO",
    "NodePatchRequest",
    "NodeSchemaDTO",
    "WorkflowDTO",
    "WorkflowSanitizedPayload",
    "WorkflowCreateRequest",
    "WorkflowUpdateRequest",
    "WorkflowListResponse",
    "ExecutionDTO",
    "ExecutionDetailDTO",
    "ExecutionListResponse",
    "WorkflowValidationResultDTO",
    "AIAgentValidationResultDTO",
    "DiagnosticsReportDTO",
    "SelfHealingReportDTO",
    "TemplateSummaryDTO",
    "TemplateDetailDTO",
    "SnapshotDTO",
    "RollbackResultDTO",
]

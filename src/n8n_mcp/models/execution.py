"""
Execution DTO specifications for n8n runs and forensics.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import Field
from n8n_mcp.models.base import N8nBaseModel


class ExecutionDTO(N8nBaseModel):
    """Summary execution record from n8n GET /api/v1/executions."""

    id: str
    finished: bool = False
    mode: str = "integrated"
    retry_of: Optional[str] = Field(default=None, alias="retryOf")
    retry_success_id: Optional[str] = Field(default=None, alias="retrySuccessId")
    status: str = "unknown"
    started_at: Optional[str] = Field(default=None, alias="startedAt")
    stopped_at: Optional[str] = Field(default=None, alias="stoppedAt")
    workflow_id: Optional[str] = Field(default=None, alias="workflowId")


class ExecutionDetailDTO(ExecutionDTO):
    """Detailed execution trace including node results and error structures."""

    data: Optional[Dict[str, Any]] = None


class ExecutionListResponse(N8nBaseModel):
    """Paginated list of execution summaries."""

    data: List[ExecutionDTO] = Field(default_factory=list)
    next_cursor: Optional[str] = Field(default=None, alias="nextCursor")

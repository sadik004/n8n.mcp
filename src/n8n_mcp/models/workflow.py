"""
Workflow DTO specifications and payload sanitization models.
Enforces strict separation of mutable fields from n8n read-only metadata to prevent HTTP 400 Bad Request errors.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import Field
from n8n_mcp.models.base import N8nBaseModel
from n8n_mcp.models.node import NodeDTO


class WorkflowSanitizedPayload(N8nBaseModel):
    """
    Sanitized mutable payload for n8n PUT and POST requests.
    Strictly encapsulates mutable fields: name, nodes, connections, settings, pinData.
    Strips read-only fields (id, versionId, createdAt, updatedAt, triggerCount, tags, active).
    """

    name: str
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    connections: Dict[str, Any] = Field(default_factory=dict)
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict)
    pin_data: Optional[Dict[str, Any]] = Field(default=None, alias="pinData")

    @classmethod
    def from_workflow(cls, workflow: WorkflowDTO | Dict[str, Any]) -> WorkflowSanitizedPayload:
        """Extract only mutable fields from a full workflow object or dictionary."""
        if isinstance(workflow, dict):
            raw = workflow
        else:
            raw = workflow.model_dump(by_alias=True)

        raw_nodes = raw.get("nodes", [])
        serialized_nodes: List[Dict[str, Any]] = []
        for n in raw_nodes:
            if isinstance(n, dict):
                serialized_nodes.append(n)
            elif isinstance(n, NodeDTO):
                serialized_nodes.append(n.model_dump(by_alias=True, exclude_unset=True))
            else:
                serialized_nodes.append(dict(n))

        return cls(
            name=raw.get("name", "Untitled Workflow"),
            nodes=serialized_nodes,
            connections=raw.get("connections", {}),
            settings=raw.get("settings", {}),
            pin_data=raw.get("pinData") or raw.get("pin_data"),
        )

    def to_api_dict(self) -> Dict[str, Any]:
        """Serialize payload strictly formatted for n8n PUT/POST endpoints."""
        data = self.model_dump(by_alias=True, exclude_unset=True)
        if self.pin_data is None and "pinData" in data:
            del data["pinData"]
        return data


class WorkflowDTO(N8nBaseModel):
    """Full workflow representation retrieved from n8n GET API."""

    id: str
    name: str
    active: bool = False
    nodes: List[NodeDTO] = Field(default_factory=list)
    connections: Dict[str, Any] = Field(default_factory=dict)
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict)
    pin_data: Optional[Dict[str, Any]] = Field(default=None, alias="pinData")
    version_id: Optional[str] = Field(default=None, alias="versionId")
    created_at: Optional[str] = Field(default=None, alias="createdAt")
    updated_at: Optional[str] = Field(default=None, alias="updatedAt")
    trigger_count: Optional[int] = Field(default=0, alias="triggerCount")
    tags: Optional[List[Any]] = Field(default_factory=list)


class WorkflowCreateRequest(N8nBaseModel):
    """Specification for creating a new workflow."""

    name: str
    nodes: List[NodeDTO] = Field(default_factory=list)
    connections: Dict[str, Any] = Field(default_factory=dict)
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict)


class WorkflowUpdateRequest(N8nBaseModel):
    """Specification for updating full workflow definition."""

    name: Optional[str] = None
    nodes: Optional[List[NodeDTO]] = None
    connections: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None


class WorkflowListResponse(N8nBaseModel):
    """Paginated list of workflows."""

    data: List[WorkflowDTO] = Field(default_factory=list)
    next_cursor: Optional[str] = Field(default=None, alias="nextCursor")

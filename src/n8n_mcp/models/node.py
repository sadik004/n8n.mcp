"""
Node DTO specifications for n8n workflows.
Supports parameters, credentials, canvas coordinates, and patch contracts.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import Field
from n8n_mcp.models.base import N8nBaseModel


class NodeConnectionItemDTO(N8nBaseModel):
    """Single node target connection in n8n execution graph."""

    node: str
    type: str = "main"
    index: int = 0


class NodeDTO(N8nBaseModel):
    """Full node definition inside n8n workflow canvas."""

    id: Optional[str] = None
    name: str
    type: str
    type_version: float | int = Field(default=1, alias="typeVersion")
    position: List[float] = Field(default_factory=lambda: [0.0, 0.0])
    parameters: Dict[str, Any] = Field(default_factory=dict)
    credentials: Optional[Dict[str, Any]] = None
    disabled: bool = False
    notes_in_flow: Optional[bool] = Field(default=None, alias="notesInFlow")


class NodePatchRequest(N8nBaseModel):
    """Targeted partial update request for a single node, saving 85-90% tokens."""

    node_name: str
    parameters: Optional[Dict[str, Any]] = None
    position: Optional[List[float]] = None
    disabled: Optional[bool] = None


class NodeSchemaDTO(N8nBaseModel):
    """Anti-hallucination ground-truth contract for n8n node parameter schemas."""

    name: str
    display_name: str = Field(alias="displayName")
    description: str
    category: str = "Development"
    properties: List[Dict[str, Any]] = Field(default_factory=list)
    operations: List[str] = Field(default_factory=list)
    credentials_required: List[str] = Field(default_factory=list, alias="credentialsRequired")

"""
Template DTO specifications for n8n community and official workflow registries.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import Field
from n8n_mcp.models.base import N8nBaseModel


class TemplateSummaryDTO(N8nBaseModel):
    """Brief summary record for templates found in n8n registry."""

    id: int | str
    name: str
    description: Optional[str] = None
    total_views: Optional[int] = Field(default=0, alias="totalViews")
    categories: Optional[List[str]] = Field(default_factory=list)
    author: Optional[Dict[str, Any]] = None


class TemplateDetailDTO(N8nBaseModel):
    """Full template blueprint containing deployable workflow graph."""

    id: int | str
    name: str
    description: Optional[str] = None
    workflow: Dict[str, Any] = Field(default_factory=dict)

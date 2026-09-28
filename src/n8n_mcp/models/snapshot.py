"""
Snapshot and Rollback DTO specifications for 1-click safe workflow version recovery.
"""

from __future__ import annotations
from typing import Any, Dict
from n8n_mcp.models.base import N8nBaseModel


class SnapshotDTO(N8nBaseModel):
    """Local immutable snapshot of a workflow state prior to modification."""

    workflow_id: str
    timestamp: str
    version_hash: str
    workflow_data: Dict[str, Any]


class RollbackResultDTO(N8nBaseModel):
    """Confirmation record following a 1-click snapshot restoration."""

    workflow_id: str
    restored_version_hash: str
    timestamp: str
    status: str = "restored"

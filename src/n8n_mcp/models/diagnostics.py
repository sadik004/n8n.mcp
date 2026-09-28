"""
Diagnostics and Self-Healing DTO specifications for n8n workflows and runs.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from n8n_mcp.models.base import N8nBaseModel


class WorkflowValidationResultDTO(N8nBaseModel):
    """Validation report for workflow DAG topology and expression syntax."""

    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    dangling_nodes: List[str] = []
    cycle_detected: bool = False
    syntax_errors: List[str] = []


class AIAgentValidationResultDTO(N8nBaseModel):
    """Validation report specifically for modern n8n LangChain AI Agent clusters."""

    is_valid: bool
    agent_nodes: List[str] = []
    missing_connections: Dict[str, List[str]] = {}
    errors: List[str] = []


class DiagnosticsReportDTO(N8nBaseModel):
    """Structured Root Cause Analysis (RCA) report for a crashed execution."""

    execution_id: str
    workflow_id: Optional[str] = None
    crashed_node: Optional[str] = None
    error_type: str = "Unknown"
    error_message: str = ""
    stack_trace: Optional[str] = None
    root_cause_analysis: str = ""
    remediation_suggestions: List[str] = []


class SelfHealingReportDTO(N8nBaseModel):
    """Outcome report for bounded autonomous self-healing execution loop."""

    execution_id: str
    workflow_id: str
    attempt: int = 1
    success: bool = False
    patched_node: Optional[str] = None
    patch_summary: Optional[Dict[str, Any]] = None
    new_execution_id: Optional[str] = None
    status: str = "healed"

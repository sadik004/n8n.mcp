"""
Execution Diagnostics and Root Cause Analysis (RCA) Engine.
Pinpoints crashing nodes, categorizes runtime faults, and synthesizes actionable remediation advice.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional, Tuple

from n8n_mcp.models.diagnostics import DiagnosticsReportDTO
from n8n_mcp.models.execution import ExecutionDetailDTO

logger = logging.getLogger("n8n_mcp.diagnostics")


class ExecutionDiagnosticsEngine:
    """Intelligent forensics engine analyzing n8n execution traces and runData graphs."""

    ERROR_TAXONOMY = {
        "AUTH_FAILURE": ("401", "403", "unauthorized", "authorization", "forbidden", "credential", "api key", "auth"),
        "NOT_FOUND": ("404", "not found", "cannot find"),
        "CONNECTION_REFUSED": ("econnrefused", "connection refused", "connect refused", "connection failed"),
        "TIMEOUT": ("timeout", "timed out", "etimedout", "esockettimedout"),
        "SYNTAX_ERROR": ("syntaxerror", "unexpected token", "json.parse", "parsing error", "invalid json"),
        "RATE_LIMITED": ("429", "too many requests", "rate limit", "rate limited"),
    }

    def _extract_crashed_node_and_error(
        self, data: Dict[str, Any]
    ) -> Tuple[Optional[str], str, Optional[str]]:
        """Scans resultData and runData to isolate the exact crashed node name and error text."""
        result_data = data.get("resultData", {})
        root_error = result_data.get("error", {})

        crashed_node = None
        error_msg = ""
        stack_trace = None

        if isinstance(root_error, dict):
            error_msg = root_error.get("message") or root_error.get("description") or ""
            stack_trace = root_error.get("stack")
            node_obj = root_error.get("node")
            if isinstance(node_obj, dict):
                crashed_node = node_obj.get("name")

        # Fallback to inspecting runData if node was not directly identified
        run_data = result_data.get("runData") or data.get("runData", {})
        if isinstance(run_data, dict):
            for node_name, runs in run_data.items():
                if isinstance(runs, list):
                    for run_item in runs:
                        if isinstance(run_item, dict) and "error" in run_item:
                            err_info = run_item["error"]
                            if isinstance(err_info, dict):
                                crashed_node = crashed_node or node_name
                                error_msg = error_msg or err_info.get("message", "")
                                stack_trace = stack_trace or err_info.get("stack")

        return crashed_node, error_msg, stack_trace

    def _classify_error_type(self, error_msg: str, stack_trace: Optional[str]) -> str:
        """Matches error signatures against domain taxonomy."""
        combined_text = f"{error_msg} {stack_trace or ''}".lower()
        if not combined_text.strip():
            return "NO_ERROR"

        for err_type, keywords in self.ERROR_TAXONOMY.items():
            if any(k in combined_text for k in keywords):
                return err_type

        return "GENERIC_RUNTIME_ERROR"

    def _generate_rca_and_remediations(
        self, error_type: str, crashed_node: Optional[str], error_msg: str
    ) -> Tuple[str, List[str]]:
        """Synthesizes human and LLM-actionable RCA explanations and remedies."""
        node_prefix = f"In node '{crashed_node}': " if crashed_node else ""

        if error_type == "AUTH_FAILURE":
            rca = f"{node_prefix}Authentication credentials were rejected by the external service."
            remedies = [
                "Inspect API key, bearer token, or OAuth2 credential status in n8n credential settings.",
                "Verify required authentication headers (e.g. Authorization or X-API-KEY).",
                "Check for expired tokens and refresh authorization grant.",
            ]
        elif error_type == "CONNECTION_REFUSED":
            rca = f"{node_prefix}Target host connection refused. If calling a local service from n8n Docker, localhost will fail."
            remedies = [
                "When calling local services from Dockerized n8n, change 'localhost' to 'host.docker.internal'.",
                "Verify target service is actively running and bound to 0.0.0.0, not just 127.0.0.1.",
                "Inspect firewall and port availability on the target host.",
            ]
        elif error_type == "NOT_FOUND":
            rca = f"{node_prefix}Requested URL path or API resource returned HTTP 404 Not Found."
            remedies = [
                "Verify endpoint URL path and ensure no typos exist in query parameters.",
                "Confirm target ID or resource slug exists in upstream database.",
            ]
        elif error_type == "TIMEOUT":
            rca = f"{node_prefix}Upstream service did not reply within the configured timeout threshold."
            remedies = [
                "Increase node request timeout in node options settings.",
                "Ensure upstream server is not under heavy load or throttling incoming requests.",
            ]
        elif error_type == "SYNTAX_ERROR":
            rca = f"{node_prefix}Payload formatting or code parsing failure encountered."
            remedies = [
                "Validate JSON body structure and ensure all expressions have matching closed braces ({{ ... }}).",
                "Review code syntax in JavaScript / Python Code nodes using node linter.",
            ]
        elif error_type == "RATE_LIMITED":
            rca = f"{node_prefix}Upstream API rate limit quota exceeded (HTTP 429 Too Many Requests)."
            remedies = [
                "Add wait/delay nodes between batch iterations.",
                "Implement exponential backoff retry in node execution settings.",
            ]
        elif error_type == "NO_ERROR":
            rca = "Execution completed without error."
            remedies = []
        else:
            rca = f"{node_prefix}Execution halted due to unexpected runtime exception: {error_msg}"
            remedies = [
                "Examine node inputs and verify previous node data schema.",
                "Inspect error stack trace for variable reference errors or null pointers.",
            ]

        return rca, remedies

    def diagnose_execution(
        self, execution: ExecutionDetailDTO | Dict[str, Any]
    ) -> DiagnosticsReportDTO:
        """Executes full diagnostic pass across execution trace."""
        if isinstance(execution, ExecutionDetailDTO):
            exec_id = execution.id
            wf_id = execution.workflow_id
            status = execution.status
            exec_data = execution.data or {}
        else:
            exec_id = str(execution.get("id", "unknown"))
            wf_id = execution.get("workflowId")
            status = execution.get("status", "unknown")
            exec_data = execution.get("data", {})

        if status == "success":
            return DiagnosticsReportDTO(
                execution_id=exec_id,
                workflow_id=wf_id,
                crashed_node=None,
                error_type="NO_ERROR",
                error_message="",
                root_cause_analysis="Execution completed successfully with exit code 0.",
                remediation_suggestions=[],
            )

        crashed_node, error_msg, stack_trace = self._extract_crashed_node_and_error(exec_data)
        error_type = self._classify_error_type(error_msg, stack_trace)
        rca, remedies = self._generate_rca_and_remediations(error_type, crashed_node, error_msg)

        return DiagnosticsReportDTO(
            execution_id=exec_id,
            workflow_id=wf_id,
            crashed_node=crashed_node,
            error_type=error_type,
            error_message=error_msg,
            stack_trace=stack_trace,
            root_cause_analysis=rca,
            remediation_suggestions=remedies,
        )

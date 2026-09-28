"""
Autonomous Self-Healing Loop for n8n executions.
Inspects failure -> diagnoses crashed node -> applies parameter patch -> retries execution -> confirms recovery.
Bounded by strict max_attempts to prevent runaway loops.
"""

from __future__ import annotations
import logging
from typing import Any, Dict, Optional

from n8n_mcp.engine.diagnostics import ExecutionDiagnosticsEngine
from n8n_mcp.models.diagnostics import SelfHealingReportDTO
from n8n_mcp.models.node import NodePatchRequest

logger = logging.getLogger("n8n_mcp.healer")


class AutonomousSelfHealer:
    """Orchestrates bounded self-healing recovery loops for crashed workflow runs."""

    def __init__(
        self,
        client: Any,
        patcher: Any,
        diagnostics: Optional[ExecutionDiagnosticsEngine] = None,
        max_attempts: int = 2,
    ):
        self.client = client
        self.patcher = patcher
        self.diagnostics = diagnostics or ExecutionDiagnosticsEngine()
        self.max_attempts = max(1, max_attempts)

    async def heal_execution(
        self,
        execution_id: str,
        repair_parameters: Dict[str, Any],
        target_node_name: Optional[str] = None,
    ) -> SelfHealingReportDTO:
        """
        Executes bounded self-healing cycle:
        1. Diagnoses current execution error and crashed node
        2. Applies patch via WorkflowPatcher (with pre-repair snapshot)
        3. Invokes client.retry_execution
        4. Inspects retried execution status and validates recovery
        """
        current_id = execution_id
        last_crashed_node = target_node_name
        workflow_id = "unknown"

        for attempt in range(1, self.max_attempts + 1):
            logger.info(f"Self-healing attempt {attempt}/{self.max_attempts} on execution {current_id}")

            try:
                exec_obj = await self.client.get_execution(current_id, include_data=True)
                diag_report = self.diagnostics.diagnose_execution(exec_obj)
                workflow_id = exec_obj.workflow_id or workflow_id

                node_to_patch = target_node_name or diag_report.crashed_node
                last_crashed_node = node_to_patch

                if not node_to_patch:
                    logger.warning(f"Could not isolate crashed node in execution {current_id}")
                    break

                # 1. Apply diff patch to target node
                patch_req = NodePatchRequest(node_name=node_to_patch, parameters=repair_parameters)
                await self.patcher.patch_node(workflow_id, patch_req)

                # 2. Trigger execution retry
                retry_res = await self.client.retry_execution(current_id)
                new_exec_id = retry_res.get("id") or current_id

                # 3. Check status of retried run
                retried_obj = await self.client.get_execution(new_exec_id, include_data=True)

                if retried_obj.status == "success":
                    logger.info(f"Execution {execution_id} successfully self-healed in attempt {attempt}!")
                    return SelfHealingReportDTO(
                        execution_id=execution_id,
                        workflow_id=workflow_id,
                        attempt=attempt,
                        success=True,
                        patched_node=node_to_patch,
                        patch_summary=repair_parameters,
                        new_execution_id=new_exec_id,
                        status="healed",
                    )

                current_id = new_exec_id

            except Exception as exc:
                logger.error(f"Error during self-healing attempt {attempt}: {exc}")
                if attempt == self.max_attempts:
                    break

        return SelfHealingReportDTO(
            execution_id=execution_id,
            workflow_id=workflow_id,
            attempt=self.max_attempts,
            success=False,
            patched_node=last_crashed_node,
            patch_summary=repair_parameters,
            new_execution_id=current_id if current_id != execution_id else None,
            status="failed",
        )

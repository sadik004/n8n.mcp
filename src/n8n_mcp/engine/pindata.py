"""
Safe Sandbox Testing engine with n8n Pin Data.
Injects mock data into trigger nodes to test workflows without side-effects on live systems.
"""

from __future__ import annotations
import copy
from typing import Any, Dict, List, Optional
import logging

from n8n_mcp.models.workflow import WorkflowDTO

logger = logging.getLogger("n8n_mcp.pindata")


class PinDataManager:
    """Manages pinData injections strictly keyed by Node Name and wrapped in [{'json': ...}]."""

    def __init__(self, client: Any):
        self.client = client

    @staticmethod
    def normalize_pin_data(data: Any) -> List[Dict[str, Any]]:
        """
        Smart wrapping: Ensures data strictly conforms to n8n pinData schema:
        [{"json": {...}}, ...]
        """
        if isinstance(data, list):
            # Check if elements are already formatted as {"json": ...}
            is_already_wrapped = all(
                isinstance(item, dict) and "json" in item and len(item) == 1 for item in data
            )
            if is_already_wrapped:
                return data
            # Wrap each element into {"json": item}
            return [{"json": item if isinstance(item, dict) else {"value": item}} for item in data]

        elif isinstance(data, dict):
            if "json" in data and len(data) == 1 and isinstance(data["json"], dict):
                return [data]
            return [{"json": data}]

        # Primitive value fallback
        return [{"json": {"value": data}}]

    async def set_pinned_data(self, workflow_id: str, node_name: str, data: Any) -> Dict[str, Any]:
        """
        Injects mock test data into a specific node's pinData mapping:
        pinData: { "<Node Name>": [ { "json": { ... } } ] }
        """
        workflow = await self.client.get_workflow(workflow_id)

        if isinstance(workflow, WorkflowDTO):
            wf_data = workflow.model_dump(by_alias=True)
        else:
            wf_data = copy.deepcopy(workflow)

        nodes = wf_data.get("nodes", [])
        target_node = next((n for n in nodes if n.get("name") == node_name), None)

        if not target_node:
            raise ValueError(
                f"Node '{node_name}' not found in workflow '{workflow_id}' "
                f"(valid node names: {[n.get('name') for n in nodes]})."
            )

        # Ensure pinData mapping exists
        if "pinData" not in wf_data or not isinstance(wf_data["pinData"], dict):
            wf_data["pinData"] = {}

        normalized = self.normalize_pin_data(data)
        wf_data["pinData"][node_name] = normalized

        await self.client.update_workflow(workflow_id, wf_data)

        return {
            "workflow_id": workflow_id,
            "node_name": node_name,
            "item_count": len(normalized),
            "status": "pinned",
            "message": f"Pinned data injected into node '{node_name}' successfully.",
        }

    async def clear_pinned_data(
        self, workflow_id: str, node_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Clears pinData for a specific node or for the entire workflow.
        Guarantees clean production state before publishing.
        """
        workflow = await self.client.get_workflow(workflow_id)

        if isinstance(workflow, WorkflowDTO):
            wf_data = workflow.model_dump(by_alias=True)
        else:
            wf_data = copy.deepcopy(workflow)

        if "pinData" not in wf_data or not isinstance(wf_data["pinData"], dict):
            wf_data["pinData"] = {}

        if node_name:
            if node_name in wf_data["pinData"]:
                del wf_data["pinData"][node_name]
            msg = f"Cleared pinned data for node '{node_name}'."
        else:
            wf_data["pinData"] = {}
            msg = "Cleared all pinned data for workflow."

        await self.client.update_workflow(workflow_id, wf_data)

        return {
            "workflow_id": workflow_id,
            "node_name": node_name,
            "status": "cleared",
            "message": msg,
        }

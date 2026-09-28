"""
behavioral-playwright Integration Bridge for n8n.
Generates anti-bot stealth scraping nodes that bypass Cloudflare/Turnstile and pipe unblocked data into n8n.
Handles Docker host resolution via http://host.docker.internal:8000.
"""

from __future__ import annotations
import copy
import json
import logging
from typing import Any, Dict, List, Optional

from n8n_mcp.config import N8nConfig
from n8n_mcp.models.workflow import WorkflowDTO

logger = logging.getLogger("n8n_mcp.stealth_bridge")


class StealthScraperBridge:
    """Bridges n8n workflow pipelines with local/remote behavioral-playwright evasion engine."""

    def __init__(self, config: Optional[N8nConfig] = None):
        self.config = config or N8nConfig()
        self.base_url = self.config.behavioral_playwright_url.rstrip("/")

    def create_stealth_node(
        self,
        node_name: str,
        target_url: str,
        selector: Optional[str] = None,
        extract_schema: Optional[Dict[str, Any]] = None,
        position: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Generates an n8n-nodes-base.httpRequest node pre-configured to communicate with behavioral-playwright.
        Enforces biometric tremor, residential proxy routing, and route-level asset abortion.
        """
        payload = {
            "url": target_url,
            "selector": selector or "body",
            "stealth_mode": True,
            "biomechanical_tremor": True,
            "route_abort_assets": True,
        }
        if extract_schema:
            payload["extract_schema"] = extract_schema

        return {
            "id": f"stealth-{node_name.lower().replace(' ', '-')[:12]}",
            "name": node_name,
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": position or [300.0, 300.0],
            "parameters": {
                "method": "POST",
                "url": f"{self.base_url}/scrape",
                "authentication": "none",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": json.dumps(payload, indent=2),
                "options": {
                    "response": {
                        "response": {
                            "responseFormat": "json",
                            "neverError": True,
                        }
                    },
                    "timeout": 60000,
                },
            },
        }

    def inject_stealth_node(
        self,
        workflow: Dict[str, Any] | WorkflowDTO,
        node_name: str,
        target_url: str,
        selector: Optional[str] = None,
        connect_from: Optional[str] = None,
        position: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Injects a pre-configured stealth scraper node into an existing workflow dictionary or DTO.
        Optionally connects it to an existing upstream trigger node.
        """
        if isinstance(workflow, WorkflowDTO):
            wf_data = workflow.model_dump(by_alias=True)
        else:
            wf_data = copy.deepcopy(workflow)

        if "nodes" not in wf_data or not isinstance(wf_data["nodes"], list):
            wf_data["nodes"] = []
        if "connections" not in wf_data or not isinstance(wf_data["connections"], dict):
            wf_data["connections"] = {}

        # 1. Create and append stealth node
        stealth_node = self.create_stealth_node(
            node_name=node_name,
            target_url=target_url,
            selector=selector,
            position=position,
        )
        wf_data["nodes"].append(stealth_node)

        # 2. Connect from source if specified
        if connect_from:
            if connect_from not in wf_data["connections"]:
                wf_data["connections"][connect_from] = {"main": [[]]}
            elif "main" not in wf_data["connections"][connect_from]:
                wf_data["connections"][connect_from]["main"] = [[]]

            target_conn = {"node": node_name, "type": "main", "index": 0}
            main_branches = wf_data["connections"][connect_from]["main"]
            if not main_branches:
                main_branches.append([target_conn])
            else:
                main_branches[0].append(target_conn)

        return wf_data

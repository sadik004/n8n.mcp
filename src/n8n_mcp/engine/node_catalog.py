"""
Anti-Hallucination Node Discovery and Schema Catalog Engine.
Pre-bundled 0ms ground-truth inspector for n8n node parameters, categories, and operations.
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from n8n_mcp.engine.exceptions import N8nNotFoundError
from n8n_mcp.models.node import NodeSchemaDTO

logger = logging.getLogger("n8n_mcp.node_catalog")


class NodeCatalogEngine:
    """Provides instant 0ms offline parameter discovery to eliminate LLM node hallucinations."""

    COMMON_ALIASES: Dict[str, str] = {
        "httprequest": "n8n-nodes-base.httpRequest",
        "http": "n8n-nodes-base.httpRequest",
        "code": "n8n-nodes-base.code",
        "javascript": "n8n-nodes-base.code",
        "python": "n8n-nodes-base.code",
        "webhook": "n8n-nodes-base.webhook",
        "schedule": "n8n-nodes-base.scheduleTrigger",
        "cron": "n8n-nodes-base.scheduleTrigger",
        "if": "n8n-nodes-base.if",
        "switch": "n8n-nodes-base.switch",
        "postgres": "n8n-nodes-base.postgres",
        "postgresql": "n8n-nodes-base.postgres",
        "slack": "n8n-nodes-base.slack",
        "telegram": "n8n-nodes-base.telegram",
        "googlesheets": "n8n-nodes-base.googleSheets",
        "sheets": "n8n-nodes-base.googleSheets",
        "openai": "@n8n/n8n-nodes-langchain.openAi",
        "agent": "@n8n/n8n-nodes-langchain.agent",
        "ai_agent": "@n8n/n8n-nodes-langchain.agent",
        "langchain": "@n8n/n8n-nodes-langchain.agent",
        "hubspot": "n8n-nodes-base.hubspot",
    }

    def __init__(self, catalog_path: Optional[Path] = None):
        if catalog_path is None:
            self.catalog_path = Path(__file__).resolve().parent.parent / "data" / "nodes_catalog.json"
        else:
            self.catalog_path = catalog_path

        self._schemas: Dict[str, NodeSchemaDTO] = {}
        self._load_catalog()

    def _load_catalog(self) -> None:
        """Loads static node catalog into indexed memory."""
        if not self.catalog_path.exists():
            logger.warning(f"Nodes catalog file not found at {self.catalog_path}")
            return

        try:
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                raw_list = json.load(f)
                for item in raw_list:
                    schema = NodeSchemaDTO.model_validate(item)
                    self._schemas[schema.name] = schema
        except Exception as exc:
            logger.error(f"Failed to load nodes catalog: {exc}")

    def search_nodes(self, query: str = "") -> List[NodeSchemaDTO]:
        """
        Search node catalog by name, display name, description, or category.
        Case-insensitive multi-field search. Empty query returns all available nodes.
        """
        if not query or not query.strip():
            return list(self._schemas.values())

        q = query.strip().lower()
        matches: List[NodeSchemaDTO] = []

        for schema in self._schemas.values():
            in_name = q in schema.name.lower()
            in_display = q in schema.display_name.lower()
            in_desc = q in schema.description.lower()
            in_category = q in schema.category.lower()
            in_ops = any(q in op.lower() for op in schema.operations)

            if in_name or in_display or in_desc or in_category or in_ops:
                matches.append(schema)

        return matches

    def get_node_schema(self, node_name_or_alias: str) -> NodeSchemaDTO:
        """
        Retrieves ground-truth parameter schema for a given node full name or friendly alias.
        Raises N8nNotFoundError if node is not found in the catalog.
        """
        raw_key = node_name_or_alias.strip()

        # 1. Exact match
        if raw_key in self._schemas:
            return self._schemas[raw_key]

        # 2. Check alias map
        alias_key = raw_key.lower().replace("-", "").replace("_", "").replace(" ", "")
        resolved_name = self.COMMON_ALIASES.get(alias_key)
        if resolved_name and resolved_name in self._schemas:
            return self._schemas[resolved_name]

        # 3. Partial lowercase fallback
        for name, schema in self._schemas.items():
            if raw_key.lower() in name.lower() or raw_key.lower() in schema.display_name.lower():
                return schema

        raise N8nNotFoundError(
            f"Node schema not found for '{node_name_or_alias}'. "
            f"Use n8n_search_nodes to browse available node specifications.",
            status_code=404,
        )

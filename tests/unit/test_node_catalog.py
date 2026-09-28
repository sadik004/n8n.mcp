"""
Unit tests for NodeCatalogEngine anti-hallucination discovery.
Testing search across keywords/categories, schema retrieval, alias normalization, and N8nNotFoundError.
"""

import pytest
from n8n_mcp.engine.node_catalog import NodeCatalogEngine
from n8n_mcp.engine.exceptions import N8nNotFoundError
from n8n_mcp.models.node import NodeSchemaDTO


@pytest.fixture
def catalog():
    return NodeCatalogEngine()


def test_search_nodes_by_keyword(catalog):
    """Verify searching finds relevant nodes by name, description, or category."""
    # 1. Search for slack
    slack_results = catalog.search_nodes("slack")
    assert len(slack_results) >= 1
    assert any(n.name == "n8n-nodes-base.slack" for n in slack_results)

    # 2. Search for AI agent
    ai_results = catalog.search_nodes("agent")
    assert len(ai_results) >= 1
    assert any("langchain.agent" in n.name for n in ai_results)

    # 3. Search for database category
    db_results = catalog.search_nodes("database")
    assert len(db_results) >= 1
    assert any(n.name == "n8n-nodes-base.postgres" for n in db_results)


def test_search_nodes_empty_and_case_insensitive(catalog):
    """Verify empty search returns all catalog items and search is case-insensitive."""
    all_nodes = catalog.search_nodes("")
    assert len(all_nodes) >= 10

    upper_results = catalog.search_nodes("WEBHOOK")
    assert len(upper_results) >= 1
    assert any(n.name == "n8n-nodes-base.webhook" for n in upper_results)


def test_get_node_schema_exact_and_alias(catalog):
    """Verify schema retrieval by exact name and friendly alias."""
    # Exact full name
    schema1 = catalog.get_node_schema("n8n-nodes-base.slack")
    assert isinstance(schema1, NodeSchemaDTO)
    assert schema1.name == "n8n-nodes-base.slack"
    assert "channel" in [p.get("name") for p in schema1.properties]

    # Friendly alias (e.g. "slack")
    schema2 = catalog.get_node_schema("slack")
    assert schema2.name == "n8n-nodes-base.slack"

    # AI Agent schema
    agent_schema = catalog.get_node_schema("@n8n/n8n-nodes-langchain.agent")
    assert agent_schema.name == "@n8n/n8n-nodes-langchain.agent"
    assert "promptType" in [p.get("name") for p in agent_schema.properties]


def test_get_node_schema_raises_not_found(catalog):
    """Verify N8nNotFoundError is raised when node does not exist in catalog."""
    with pytest.raises(N8nNotFoundError, match="Node schema not found for 'unknown.hallucinatedNode'"):
        catalog.get_node_schema("unknown.hallucinatedNode")

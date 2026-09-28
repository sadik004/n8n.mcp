"""
Unit tests for StealthScraperBridge engine.
Testing behavioral-playwright node generation, container-safe host URL resolution, and workflow injection.
"""

import pytest
from n8n_mcp.config import N8nConfig
from n8n_mcp.engine.stealth_bridge import StealthScraperBridge
from n8n_mcp.models.workflow import WorkflowDTO


@pytest.fixture
def default_bridge():
    config = N8nConfig(behavioral_playwright_url="http://host.docker.internal:8000")
    return StealthScraperBridge(config=config)


def test_generate_stealth_node_defaults(default_bridge):
    """Verify generated node is an httpRequest node targeting /scrape with anti-bot options."""
    node = default_bridge.create_stealth_node(
        node_name="Bypass Cloudflare Scraper",
        target_url="https://protected-site.com/data",
        selector=".target-data-card",
        position=[400.0, 300.0],
    )

    assert node["name"] == "Bypass Cloudflare Scraper"
    assert node["type"] == "n8n-nodes-base.httpRequest"
    assert node["position"] == [400.0, 300.0]

    params = node["parameters"]
    assert params["method"] == "POST"
    assert params["url"] == "http://host.docker.internal:8000/scrape"
    assert params["sendBody"] is True
    assert params["specifyBody"] == "json"

    # Verify anti-bot payload structure
    body = params["jsonBody"]
    assert "https://protected-site.com/data" in body
    assert ".target-data-card" in body
    assert "biomechanical_tremor" in body


def test_generate_stealth_node_custom_url():
    """Verify custom behavioral_playwright_url override is applied."""
    config = N8nConfig(behavioral_playwright_url="http://192.168.1.50:9000/")
    bridge = StealthScraperBridge(config=config)

    node = bridge.create_stealth_node(
        node_name="Local Scraper",
        target_url="https://news.ycombinator.com",
    )

    assert node["parameters"]["url"] == "http://192.168.1.50:9000/scrape"


def test_inject_stealth_node_into_workflow(default_bridge):
    """Verify injecting stealth node into an existing workflow dictionary."""
    existing_wf = {
        "name": "Pipeline with Scraper",
        "nodes": [
            {"name": "Schedule Trigger", "type": "n8n-nodes-base.scheduleTrigger", "position": [100, 200]}
        ],
        "connections": {},
    }

    updated_wf = default_bridge.inject_stealth_node(
        workflow=existing_wf,
        node_name="Stealth Fetcher",
        target_url="https://reddit.com/r/python",
        connect_from="Schedule Trigger",
    )

    # Node added
    node_names = [n["name"] for n in updated_wf["nodes"]]
    assert "Stealth Fetcher" in node_names

    # Connection created
    assert "Schedule Trigger" in updated_wf["connections"]
    targets = updated_wf["connections"]["Schedule Trigger"]["main"][0]
    assert any(conn["node"] == "Stealth Fetcher" for conn in targets)

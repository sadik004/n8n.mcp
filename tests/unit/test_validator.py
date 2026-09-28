"""
Unit tests for WorkflowValidator engine.
Testing DFS cycle detection, dangling node audits, expression syntax linter, Code node AST checks, and LangChain AI Agent port validation.
"""

import pytest
from n8n_mcp.engine.validator import WorkflowValidator
from n8n_mcp.models.diagnostics import WorkflowValidationResultDTO, AIAgentValidationResultDTO


@pytest.fixture
def validator():
    return WorkflowValidator()


def test_detect_cycle_in_dag(validator):
    """Verify DFS detects cycles (A -> B -> C -> A) in execution graph."""
    cyclic_workflow = {
        "name": "Cyclic Flow",
        "nodes": [
            {"name": "NodeA", "type": "n8n-nodes-base.httpRequest", "parameters": {}},
            {"name": "NodeB", "type": "n8n-nodes-base.code", "parameters": {}},
            {"name": "NodeC", "type": "n8n-nodes-base.slack", "parameters": {}},
        ],
        "connections": {
            "NodeA": {"main": [[{"node": "NodeB", "type": "main", "index": 0}]]},
            "NodeB": {"main": [[{"node": "NodeC", "type": "main", "index": 0}]]},
            "NodeC": {"main": [[{"node": "NodeA", "type": "main", "index": 0}]]},  # Loop!
        },
    }

    result = validator.validate_workflow(cyclic_workflow)
    assert isinstance(result, WorkflowValidationResultDTO)
    assert result.cycle_detected is True
    assert result.is_valid is False
    assert any("Cycle detected" in err for err in result.errors)


def test_detect_dangling_nodes(validator):
    """Verify disconnected/dangling nodes are identified."""
    dangling_workflow = {
        "name": "Dangling Flow",
        "nodes": [
            {"name": "Webhook", "type": "n8n-nodes-base.webhook", "parameters": {}},
            {"name": "ConnectedNode", "type": "n8n-nodes-base.code", "parameters": {}},
            {"name": "LostNode", "type": "n8n-nodes-base.slack", "parameters": {}},  # Disconnected
        ],
        "connections": {
            "Webhook": {"main": [[{"node": "ConnectedNode", "type": "main", "index": 0}]]}
        },
    }

    result = validator.validate_workflow(dangling_workflow)
    assert "LostNode" in result.dangling_nodes
    assert len(result.warnings) >= 1


def test_detect_unclosed_expressions(validator):
    """Verify unclosed expressions like '{{ $json.val' are flagged."""
    broken_expr_workflow = {
        "name": "Expression Error Flow",
        "nodes": [
            {
                "name": "API Call",
                "type": "n8n-nodes-base.httpRequest",
                "parameters": {
                    "url": "https://api.service.com/users/{{ $json.userId",  # Missing closing }}
                },
            }
        ],
        "connections": {},
    }

    result = validator.validate_workflow(broken_expr_workflow)
    assert len(result.syntax_errors) >= 1
    assert any("Unclosed expression" in err for err in result.syntax_errors)


def test_code_node_python_ast_validation(validator):
    """Verify Python code nodes are validated using ast.parse() before deployment."""
    # 1. Invalid python code
    broken_python_workflow = {
        "name": "Broken Python Code Flow",
        "nodes": [
            {
                "name": "Python Processor",
                "type": "n8n-nodes-base.code",
                "parameters": {
                    "language": "python",
                    "pythonCode": "def calculate_total(x\n    return x + 1",  # SyntaxError: missing )
                },
            }
        ],
        "connections": {},
    }

    res_broken = validator.validate_workflow(broken_python_workflow)
    assert res_broken.is_valid is False
    assert any("Python SyntaxError" in err for err in res_broken.errors)

    # 2. Valid python code
    valid_python_workflow = {
        "name": "Valid Python Code Flow",
        "nodes": [
            {
                "name": "Python Processor",
                "type": "n8n-nodes-base.code",
                "parameters": {
                    "language": "python",
                    "pythonCode": "def calculate_total(x):\n    return x + 1\nresult = calculate_total(10)",
                },
            }
        ],
        "connections": {},
    }

    res_valid = validator.validate_workflow(valid_python_workflow)
    assert not any("Python SyntaxError" in err for err in res_valid.errors)


def test_validate_ai_agent_graph_missing_language_model(validator):
    """Verify LangChain AI Agent node flags error if ai_languageModel connection is missing."""
    broken_agent_workflow = {
        "name": "Broken Agent Flow",
        "nodes": [
            {
                "name": "Customer Support Agent",
                "type": "@n8n/n8n-nodes-langchain.agent",
                "parameters": {"text": "How can I help you?"},
            }
        ],
        "connections": {},  # No ai_languageModel connected!
    }

    result = validator.validate_ai_agent_graph(broken_agent_workflow)
    assert isinstance(result, AIAgentValidationResultDTO)
    assert result.is_valid is False
    assert "Customer Support Agent" in result.agent_nodes
    assert "ai_languageModel" in result.missing_connections.get("Customer Support Agent", [])


def test_validate_ai_agent_graph_valid(validator):
    """Verify properly linked LangChain AI Agent cluster passes validation."""
    valid_agent_workflow = {
        "name": "Valid Agent Flow",
        "nodes": [
            {
                "name": "Customer Support Agent",
                "type": "@n8n/n8n-nodes-langchain.agent",
                "parameters": {},
            },
            {
                "name": "OpenAI Model",
                "type": "@n8n/n8n-nodes-langchain.openAi",
                "parameters": {"model": "gpt-4o"},
            },
        ],
        "connections": {
            "OpenAI Model": {
                "ai_languageModel": [
                    [{"node": "Customer Support Agent", "type": "ai_languageModel", "index": 0}]
                ]
            }
        },
    }

    result = validator.validate_ai_agent_graph(valid_agent_workflow)
    assert result.is_valid is True
    assert len(result.errors) == 0

"""
Workflow DAG Validator, LangChain AI Agent Linter, and Code AST Checker.
Multi-port graph traversal across standard 'main' and 'ai_*' sub-node ports.
"""

from __future__ import annotations
import ast
import logging
from typing import Any, Dict, List, Set

from n8n_mcp.models.diagnostics import WorkflowValidationResultDTO, AIAgentValidationResultDTO
from n8n_mcp.models.workflow import WorkflowDTO

logger = logging.getLogger("n8n_mcp.validator")


class WorkflowValidator:
    """Production graph intelligence engine analyzing DAG topology, syntax, and AI agent integrity."""

    AI_SUB_PORTS = {
        "ai_languageModel",
        "ai_tool",
        "ai_memory",
        "ai_outputParser",
        "ai_embedding",
        "ai_document",
        "ai_textSplitter",
    }

    def _extract_nodes_and_connections(self, workflow: Dict[str, Any] | WorkflowDTO):
        if isinstance(workflow, WorkflowDTO):
            raw_nodes = [n.model_dump(by_alias=True) for n in workflow.nodes]
            raw_conns = workflow.connections or {}
        else:
            raw_nodes = workflow.get("nodes", [])
            raw_conns = workflow.get("connections", {})
        return raw_nodes, raw_conns

    def _check_string_expressions(self, val: str, node_name: str, syntax_errors: List[str]):
        """Detects unclosed n8n curly expressions (e.g. {{ $json.foo )."""
        open_count = val.count("{{")
        close_count = val.count("}}")
        if open_count != close_count:
            syntax_errors.append(
                f"Unclosed expression detected in node '{node_name}' parameter value: '{val}'"
            )

    def _walk_parameters_for_expressions(self, data: Any, node_name: str, syntax_errors: List[str]):
        """Recursively scans parameter dictionaries/lists for expression syntax anomalies."""
        if isinstance(data, dict):
            for v in data.values():
                self._walk_parameters_for_expressions(v, node_name, syntax_errors)
        elif isinstance(data, list):
            for item in data:
                self._walk_parameters_for_expressions(item, node_name, syntax_errors)
        elif isinstance(data, str):
            if "{{" in data:
                self._check_string_expressions(data, node_name, syntax_errors)

    def validate_workflow(
        self, workflow: Dict[str, Any] | WorkflowDTO
    ) -> WorkflowValidationResultDTO:
        """
        Performs comprehensive multi-check validation:
        1. Multi-port DFS cycle detection (main and ai_*).
        2. Dangling / unreachable node audit.
        3. Expression syntax linter (unclosed {{ ... }}).
        4. Code node in-memory Python AST validation (ast.parse).
        """
        nodes, connections = self._extract_nodes_and_connections(workflow)
        node_names = [n.get("name") for n in nodes if n.get("name")]

        errors: List[str] = []
        warnings: List[str] = []
        dangling_nodes: List[str] = []
        syntax_errors: List[str] = []
        cycle_detected = False

        # Build multi-port adjacency list
        adjacency: Dict[str, Set[str]] = {name: set() for name in node_names}
        incoming_counts: Dict[str, int] = {name: 0 for name in node_names}

        for source_node, port_groups in connections.items():
            if not isinstance(port_groups, dict):
                continue
            for port_type, target_arrays in port_groups.items():
                if not isinstance(target_arrays, list):
                    continue
                for branch in target_arrays:
                    if not isinstance(branch, list):
                        continue
                    for conn in branch:
                        if isinstance(conn, dict):
                            target_node = conn.get("node")
                            if target_node in adjacency:
                                adjacency[source_node].add(target_node)
                                incoming_counts[target_node] = incoming_counts.get(target_node, 0) + 1

        # 1. DFS Cycle Detection (0 = Unvisited, 1 = Visiting, 2 = Visited)
        visited_state: Dict[str, int] = {name: 0 for name in node_names}

        def dfs_detect_cycle(current: str, path: List[str]) -> bool:
            visited_state[current] = 1
            path.append(current)

            for neighbor in adjacency.get(current, set()):
                if visited_state.get(neighbor) == 1:
                    cycle_path = " -> ".join(path + [neighbor])
                    errors.append(f"Cycle detected in execution graph: {cycle_path}")
                    return True
                if visited_state.get(neighbor) == 0:
                    if dfs_detect_cycle(neighbor, path):
                        return True

            visited_state[current] = 2
            path.pop()
            return False

        for name in node_names:
            if visited_state[name] == 0:
                if dfs_detect_cycle(name, []):
                    cycle_detected = True
                    break

        # 2. Dangling Node Detection
        if len(node_names) > 1:
            for name in node_names:
                outgoing_count = len(adjacency.get(name, set()))
                incoming_count = incoming_counts.get(name, 0)
                if outgoing_count == 0 and incoming_count == 0:
                    dangling_nodes.append(name)
                    warnings.append(f"Node '{name}' is dangling (no incoming or outgoing connections).")

        # 3. Expression Syntax Linter & 4. Python Code AST Validation
        for node in nodes:
            n_name = node.get("name", "Unknown")
            n_type = node.get("type", "")
            params = node.get("parameters", {})

            # Scan expressions in parameters
            self._walk_parameters_for_expressions(params, n_name, syntax_errors)

            # Python AST parsing for Code nodes
            if n_type == "n8n-nodes-base.code" and params.get("language") == "python":
                py_code = params.get("pythonCode", "")
                if py_code:
                    try:
                        ast.parse(py_code)
                    except SyntaxError as syn_err:
                        err_msg = f"Node '{n_name}' contains Python SyntaxError at line {syn_err.lineno}: {syn_err.msg}"
                        errors.append(err_msg)

        is_valid = (not cycle_detected) and (len(errors) == 0) and (len(syntax_errors) == 0)

        return WorkflowValidationResultDTO(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            dangling_nodes=dangling_nodes,
            cycle_detected=cycle_detected,
            syntax_errors=syntax_errors,
        )

    def validate_ai_agent_graph(
        self, workflow: Dict[str, Any] | WorkflowDTO
    ) -> AIAgentValidationResultDTO:
        """
        Validates LangChain AI Agent clusters (@n8n/n8n-nodes-langchain.agent).
        Ensures mandatory ai_languageModel connection is active before deployment.
        """
        nodes, connections = self._extract_nodes_and_connections(workflow)

        agent_nodes = [
            n.get("name") for n in nodes if "langchain.agent" in n.get("type", "").lower()
        ]

        missing_connections: Dict[str, List[str]] = {}
        errors: List[str] = []

        for agent in agent_nodes:
            has_language_model = False

            # Check connections where model is source and agent is target
            for src_node, ports in connections.items():
                if isinstance(ports, dict):
                    for port_name in ("ai_languageModel", "ai_model"):
                        if port_name in ports:
                            branches = ports[port_name]
                            for branch in branches:
                                for conn in branch:
                                    if isinstance(conn, dict) and conn.get("node") == agent:
                                        has_language_model = True
                                        break

            # Check connections where agent is source and model is target
            if agent in connections and isinstance(connections[agent], dict):
                agent_ports = connections[agent]
                for port_name in ("ai_languageModel", "ai_model"):
                    if port_name in agent_ports and agent_ports[port_name]:
                        has_language_model = True
                        break

            if not has_language_model:
                missing = missing_connections.setdefault(agent, [])
                missing.append("ai_languageModel")
                errors.append(
                    f"AI Agent node '{agent}' is missing mandatory 'ai_languageModel' connection."
                )

        is_valid = len(errors) == 0

        return AIAgentValidationResultDTO(
            is_valid=is_valid,
            agent_nodes=agent_nodes,
            missing_connections=missing_connections,
            errors=errors,
        )

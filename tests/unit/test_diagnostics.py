"""
Unit tests for ExecutionDiagnosticsEngine.
Testing error trace parsing, crashed node identification, error taxonomy classification, and RCA synthesis.
"""

import pytest
from n8n_mcp.engine.diagnostics import ExecutionDiagnosticsEngine
from n8n_mcp.models.diagnostics import DiagnosticsReportDTO
from n8n_mcp.models.execution import ExecutionDetailDTO


@pytest.fixture
def diagnostics():
    return ExecutionDiagnosticsEngine()


def test_diagnose_auth_failure(diagnostics):
    """Verify HTTP 401/403 errors are classified as AUTH_FAILURE with target node extracted."""
    failed_execution = ExecutionDetailDTO(
        id="exec-401",
        workflow_id="wf-lead-gen",
        status="error",
        finished=True,
        data={
            "resultData": {
                "error": {
                    "message": "Authorization failed - please check your credentials",
                    "description": "401 - Unauthorized",
                    "node": {"name": "CRM Sync", "type": "n8n-nodes-base.httpRequest"},
                }
            }
        },
    )

    report = diagnostics.diagnose_execution(failed_execution)
    assert isinstance(report, DiagnosticsReportDTO)
    assert report.execution_id == "exec-401"
    assert report.workflow_id == "wf-lead-gen"
    assert report.crashed_node == "CRM Sync"
    assert report.error_type == "AUTH_FAILURE"
    assert "credential" in report.root_cause_analysis.lower()
    assert len(report.remediation_suggestions) >= 1


def test_diagnose_crashed_node_from_rundata(diagnostics):
    """Verify crashed node is identified from runData when resultData.error.node is missing."""
    failed_execution = ExecutionDetailDTO(
        id="exec-rundata-err",
        workflow_id="wf-analytics",
        status="error",
        finished=True,
        data={
            "resultData": {"error": {"message": "Connection refused to database"}},
            "runData": {
                "Webhook Trigger": [{"hints": []}],
                "Postgres Insert": [
                    {
                        "error": {
                            "message": "connect ECONNREFUSED 127.0.0.1:5432",
                            "stack": "Error: connect ECONNREFUSED...",
                        }
                    }
                ],
            },
        },
    )

    report = diagnostics.diagnose_execution(failed_execution)
    assert report.crashed_node == "Postgres Insert"
    assert report.error_type == "CONNECTION_REFUSED"
    assert any("database" in s.lower() or "host" in s.lower() for s in report.remediation_suggestions)


def test_diagnose_clean_execution(diagnostics):
    """Verify diagnosing a successful execution reports no crashed node."""
    clean_execution = ExecutionDetailDTO(
        id="exec-clean",
        workflow_id="wf-success",
        status="success",
        finished=True,
        data={"resultData": {"runData": {"Node1": [{"data": {}}]}}},
    )

    report = diagnostics.diagnose_execution(clean_execution)
    assert report.crashed_node is None
    assert report.error_type == "NO_ERROR"

"""Tests for workflow launcher and crash reporter."""
import json
import os
import tempfile
from unittest.mock import patch

from hackeragent.core.crash_reporter import list_crashes, report_crash
from hackeragent.core.workflow_launcher import list_workflows, load_workflow_prompt, resolve_workflow


def test_list_workflows_returns_aliases():
    wfs = list_workflows()
    # Default repo has these workflows
    assert "bug-bounty" in wfs or "ctf" in wfs


def test_resolve_workflow_by_alias():
    p = resolve_workflow("bug-bounty")
    if p is not None:
        assert p.is_file()
        assert "bug-bounty" in p.stem


def test_resolve_workflow_unknown_returns_none():
    assert resolve_workflow("nonexistent-xyz") is None


def test_load_workflow_prompt_returns_string():
    wf = load_workflow_prompt("bug-bounty")
    if wf is not None:
        assert "AKTİF WORKFLOW" in wf
        assert len(wf) > 100


def test_load_workflow_prompt_unknown_returns_none():
    assert load_workflow_prompt("definitely-not-a-workflow") is None


def test_report_crash_writes_file():
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(os.environ, {"HACKERAGENT_HOME": tmp}):
            try:
                raise ValueError("test error")
            except ValueError as e:
                path = report_crash("test_component", extra={"foo": "bar"}, exc=e)
            assert path is not None
            assert path.is_file()
            data = json.loads(path.read_text())
            assert data["exception_type"] == "ValueError"
            assert data["message"] == "test error"
            assert data["component"] == "test_component"
            assert data["extra"] == {"foo": "bar"}


def test_list_crashes_returns_recent():
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(os.environ, {"HACKERAGENT_HOME": tmp}):
            try:
                raise RuntimeError("crash1")
            except RuntimeError as e:
                report_crash("comp1", exc=e)
            crashes = list_crashes(limit=10)
            assert len(crashes) >= 1
            assert crashes[0]["exception_type"] == "RuntimeError"


def test_list_crashes_empty_dir():
    with tempfile.TemporaryDirectory() as tmp:
        with patch.dict(os.environ, {"HACKERAGENT_HOME": tmp}):
            crashes = list_crashes()
            assert crashes == []

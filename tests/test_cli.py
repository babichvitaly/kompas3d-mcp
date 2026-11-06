import json
import subprocess
import sys

import pytest

from kompas_mcp import cli
from kompas_mcp.cli import main, read_json


@pytest.mark.parametrize("contents", ['{"a":1,"a":2}', '{"a":NaN}', '[]'])
def test_input_json_rejects_ambiguous_or_nonfinite_data(tmp_path, contents):
    source = tmp_path / "plan.json"
    source.write_text(contents)
    with pytest.raises(ValueError):
        read_json(source)


def test_report_rejection_precedes_any_copy(tmp_path, capsys):
    report = tmp_path / "report.json"
    report.write_text("do not change")
    assert main(["package-stage", "--plan", str(tmp_path / "missing-plan.json"),
                 "--destination", str(tmp_path / "output"), "--report", str(report)]) == 1
    assert not (tmp_path / "output").exists()
    assert report.read_text() == "do not change"
    assert json.loads(capsys.readouterr().out)["phase"] == "failed"


def test_capability_inventory_in_fresh_process_does_not_import_com():
    code = """
import asyncio,json,sys
from kompas_mcp.cli import capabilities
value=asyncio.run(capabilities())
assert not value['worker']['sta_initialized']
assert 'pythoncom' not in sys.modules
assert 'win32com' not in sys.modules
assert value['tool_count']==len(set(value['tool_names']))
assert len(value['schema_fingerprint'])==64
print(json.dumps({'tools':value['tool_count']}))
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            timeout=15, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["tools"] >= 60


@pytest.mark.parametrize("phase,exit_code", [("failed_left_open", 1), ("complete_closed", 0)])
def test_recipe_wrapper_reconciles_exit_zero_against_fresh_terminal(tmp_path, capsys, phase, exit_code):
    target = tmp_path / "result.json"
    code = "from pathlib import Path;Path(" + repr(str(target)) + ").write_text(" + repr(
        json.dumps({"phase": phase})) + ")"
    assert main(["run-recipe", "--terminal-result", str(target), "--",
                 sys.executable, "-c", code]) == exit_code
    assert json.loads(capsys.readouterr().out)["launcher_returncode"] == 0


def test_stale_terminal_is_rejected_before_launch(tmp_path, capsys):
    target, sentinel = tmp_path / "result.json", tmp_path / "must-not-exist"
    target.write_text('{"phase":"complete_closed"}')
    assert main(["run-recipe", "--terminal-result", str(target), "--", sys.executable, "-c",
                 "from pathlib import Path;Path(" + repr(str(sentinel)) + ").touch()"]) == 1
    assert not sentinel.exists()
    assert json.loads(capsys.readouterr().out)["phase"] == "failed"


def test_result_path_lease_prevents_a_second_producer(tmp_path, capsys):
    target, sentinel = tmp_path / "result.json", tmp_path / "must-not-exist"
    lease = target.with_name(target.name + ".recipe-lease.json")
    lease.write_text('{"job_id":"already-reserved"}')
    assert main(["run-recipe", "--terminal-result", str(target), "--", sys.executable, "-c",
                 "from pathlib import Path;Path(" + repr(str(sentinel)) + ").touch()"]) == 1
    assert not sentinel.exists()
    assert json.loads(lease.read_text())["job_id"] == "already-reserved"
    assert json.loads(capsys.readouterr().out)["phase"] == "failed"


def test_interrupted_wait_does_not_terminate_uncertain_child(tmp_path, monkeypatch, capsys):
    class Child:
        pid = 12345

        def wait(self):
            raise KeyboardInterrupt

        def kill(self):
            pytest.fail("An uncertain native operation must not be killed")

    monkeypatch.setattr(cli.subprocess, "Popen", lambda command: Child())
    target = tmp_path / "result.json"
    with pytest.raises(KeyboardInterrupt):
        main(["run-recipe", "--terminal-result", str(target), "--", "synthetic-recipe"])
    assert json.loads(capsys.readouterr().out)["phase"] == "reconciliation_required"
    assert target.with_name(target.name + ".recipe-lease.json").exists()

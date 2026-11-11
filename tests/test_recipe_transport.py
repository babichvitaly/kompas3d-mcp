"""Argv-envelope tests on the host; actual PowerShell/prlctl acceptance pending."""

import base64
import json
import subprocess
import sys

import pytest

from kompas_mcp.cli import main
from kompas_mcp.recipe_transport import BOOTSTRAP, encoded_recipe_command


@pytest.mark.parametrize('path', [r'C:\owned\result.json', r'C:\own folder\результат.json',
    r'\\server\share\own folder\result.json', 'C:\\ends with space\\',
    r'C:\quote " literal\file.json'])
def test_windows_drive_and_unc_argv_roundtrip_without_double_escape(tmp_path, path):
    output = tmp_path / 'argv.json'
    argv = [sys.executable, '-c',
            'import json,sys;open(sys.argv[1],"w").write(json.dumps(sys.argv[2:]))',
            str(output), '--terminal-result', path, '', 'literal "quotes"', '$notExpanded', "O'Brien"]
    envelope = encoded_recipe_command(r'C:\Python folder\python.exe', argv)
    script = base64.b64decode(envelope['powershell_argv'][-1]).decode('utf-16-le')
    assert script == envelope['script']
    assert json.loads(base64.b64decode(envelope['payload'])) == argv
    # Execute the same Python bootstrap with harmless synthetic argv. No shell/VM/CAD.
    subprocess.run([sys.executable, '-c', BOOTSTRAP, envelope['payload']], check=True, timeout=10)
    assert json.loads(output.read_text()) == argv[4:]
    assert not envelope['automatic_retry']


def test_python_executable_uses_powershell_literal_quoting():
    e = encoded_recipe_command("C:\\O'Brien\\python.exe", ['synthetic-command'])
    assert "'C:\\O''Brien\\python.exe'" in e['script']


@pytest.mark.parametrize('python,argv', [('relative.exe', ['x']), ('C:relative.exe', ['x']), (r'C:\python.exe', []),
                                       (r'C:\python.exe', ['x', '\0'])])
def test_transport_rejects_ambiguous_input(python, argv):
    with pytest.raises(ValueError):
        encoded_recipe_command(python, argv)


def test_wrong_terminal_path_after_recipe_ran_never_reruns_mutation(tmp_path, capsys):
    actual, requested, count = [tmp_path / n for n in ['actual.json', 'missing.json', 'count.txt']]
    code = ('from pathlib import Path;'
            f'Path({str(actual)!r}).write_text(\'{{"phase":"complete_closed"}}\');'
            f'p=Path({str(count)!r});p.write_text(p.read_text()+"1" if p.exists() else "1")')
    argv = ['run-recipe', '--terminal-result', str(requested), '--', sys.executable, '-c', code]
    assert main(argv) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['phase'] == 'reconciliation_required' and result['recipe_started']
    assert result['execution_status'] == 'unreported' and not result['retry_allowed']
    assert actual.exists() and count.read_text() == '1'
    from kompas_mcp.job_results import verify_result_file

    assert verify_result_file(actual)['exit_code'] == 0
    assert count.read_text() == '1'
    assert main(argv) == 1  # existing path lease blocks a second producer, not a new execution
    capsys.readouterr()
    assert count.read_text() == '1'

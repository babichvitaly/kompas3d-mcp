"""Installation must preserve user configuration and back up changed skills."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

INSTALLER = Path(__file__).resolve().parents[1] / "scripts" / "install.py"


def install(home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INSTALLER), *args],
        env={**os.environ, "CODEX_HOME": str(home)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_install_preserves_config_and_is_repeatable(tmp_path):
    config = tmp_path / "config.toml"
    original = '# Personal settings\nmodel = "example"\n'
    config.write_text(original, encoding="utf-8")
    assert install(tmp_path).returncode == 0
    installed = config.read_text(encoding="utf-8")
    assert installed.startswith(original)
    assert tomllib.loads(installed)["mcp_servers"]["kompas3d"]["command"] == sys.executable
    assert (tmp_path / "config.toml.before-kompas3d").read_text() == original
    assert len(list((tmp_path / "skills").glob("*/SKILL.md"))) == 3
    assert install(tmp_path).returncode == 0
    assert config.read_text(encoding="utf-8") == installed


def test_conflicting_server_does_not_install_skills(tmp_path):
    config = tmp_path / "config.toml"
    original = '[mcp_servers.kompas3d]\ncommand = "other-server"\n'
    config.write_text(original, encoding="utf-8")
    assert install(tmp_path).returncode != 0
    assert config.read_text(encoding="utf-8") == original
    assert not (tmp_path / "skills").exists()


def test_skill_update_requires_flag_and_keeps_backup(tmp_path):
    assert install(tmp_path).returncode == 0
    skill = tmp_path / "skills" / "kompas-api" / "SKILL.md"
    skill.write_text("Personal modification", encoding="utf-8")
    assert install(tmp_path).returncode != 0
    assert skill.read_text() == "Personal modification"
    assert install(tmp_path, "--update-skills").returncode == 0
    backups = list((tmp_path / "backups").glob("*/kompas-api/SKILL.md"))
    assert len(backups) == 1
    assert backups[0].read_text() == "Personal modification"
    assert skill.read_text(encoding="utf-8") != "Personal modification"

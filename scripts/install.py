"""Install this checkout's skills and register its local stdio server with Codex."""

import argparse
import json
import os
import shutil
import sys
import tomllib
from pathlib import Path
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-skills",
        action="store_true",
        help="Back up and replace differing copies of this project's skills",
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    codex_dir = Path(os.getenv("CODEX_HOME", str(Path.home() / ".codex")))
    config = codex_dir / "config.toml"
    original = config.read_text(encoding="utf-8") if config.exists() else ""
    data = tomllib.loads(original)
    expected = {
        "command": sys.executable,
        "args": ["-m", "kompas_mcp.server"],
        "startup_timeout_sec": 30,
        "tool_timeout_sec": 180,
    }
    existing = data.get("mcp_servers", {}).get("kompas3d")
    if existing is not None and existing != expected:
        raise SystemExit(
            "A different kompas3d server is already configured; review it before replacing."
        )
    # Preflight every destination before copying, preserving unrelated skills/config.
    sources = list((repo / "skills").glob("kompas-*"))
    changed = []
    for source in sources:
        target = codex_dir / "skills" / source.name
        if target.exists():
            for file in source.rglob("*"):
                if file.is_file():
                    dest = target / file.relative_to(source)
                    if dest.exists() and dest.read_bytes() != file.read_bytes():
                        if not args.update_skills:
                            raise SystemExit(
                                f"Existing skill differs: {dest}. Use --update-skills to back up and replace."
                            )
                        changed.append(dest)
    if changed:
        backup_dir = codex_dir / "backups" / f"kompas-skills-{uuid4().hex[:8]}"
        for dest in changed:
            backup = backup_dir / dest.relative_to(codex_dir / "skills")
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, backup)
        print(f"Previous skill files backed up to {backup_dir}")
    for source in sources:
        shutil.copytree(source, codex_dir / "skills" / source.name, dirs_exist_ok=True)
    if existing is None:
        codex_dir.mkdir(parents=True, exist_ok=True)
        section = (
            "\n[mcp_servers.kompas3d]\n"
            + "\n".join(f"{key} = {json.dumps(value)}" for key, value in expected.items())
            + "\n"
        )
        proposed = original.rstrip() + "\n" + section
        tomllib.loads(proposed)
        if config.exists():
            backup = codex_dir / "config.toml.before-kompas3d"
            if not backup.exists():
                shutil.copy2(config, backup)
        config.write_text(proposed, encoding="utf-8")
    print(f"Registered kompas3d using {sys.executable}")
    print(f"Installed {len(sources)} skills into {codex_dir / 'skills'}")
    print("Restart the MCP client to load the new server and skills.")


if __name__ == "__main__":
    main()

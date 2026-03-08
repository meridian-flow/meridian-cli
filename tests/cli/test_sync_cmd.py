from __future__ import annotations

import os
from pathlib import Path

from cyclopts import App

from meridian.cli.sync_cmd import (
    _sync_install,
    _sync_remove,
    _sync_status,
    register_sync_commands,
)
from meridian.lib.sync.config import load_sync_config
from meridian.lib.sync.lock import read_lock_file


def test_register_sync_commands_registers_group_and_subcommands() -> None:
    root_app = App(name="meridian")
    sync_app = App(name="sync")

    root_app.command(sync_app, name="sync")
    register_sync_commands(sync_app, lambda payload: None)

    assert "sync" in root_app._commands
    assert {"install", "remove", "status", "update", "upgrade"} <= set(sync_app._commands)


def test_sync_install_end_to_end_with_local_path_source(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    source_dir = tmp_path / "source"
    repo_root.mkdir()
    _write_source_skill(source_dir, "review", "Review carefully.\n")
    _write_source_agent(source_dir, "reviewer", "Review pull requests.\n")
    monkeypatch.chdir(repo_root)

    emitted: list[object] = []
    _sync_install(emitted.append, str(source_dir))

    payload = _single_payload(emitted)
    assert payload["installed"] == 2
    assert payload["errors"] == []

    config = load_sync_config(repo_root / ".meridian" / "config.toml")
    assert len(config.sources) == 1
    assert config.sources[0].name == "source"
    assert config.sources[0].path == str(source_dir)

    skill_dest = repo_root / ".agents" / "skills" / "review"
    agent_dest = repo_root / ".agents" / "agents" / "reviewer.md"
    assert skill_dest.is_dir()
    assert agent_dest.is_file()

    skill_link = repo_root / ".claude" / "skills" / "review"
    agent_link = repo_root / ".claude" / "agents" / "reviewer.md"
    assert skill_link.is_symlink()
    assert agent_link.is_symlink()
    assert os.readlink(skill_link) == "../../.agents/skills/review"
    assert os.readlink(agent_link) == "../../.agents/agents/reviewer.md"

    lock = read_lock_file(repo_root / ".meridian" / "sync.lock")
    assert set(lock.items) == {"skills/review", "agents/reviewer"}


def test_sync_status_reports_local_modifications(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    source_dir = tmp_path / "source"
    repo_root.mkdir()
    _write_source_skill(source_dir, "review", "Review carefully.\n")
    monkeypatch.chdir(repo_root)

    _sync_install(lambda payload: None, str(source_dir))
    skill_path = repo_root / ".agents" / "skills" / "review" / "SKILL.md"
    skill_path.write_text(
        "---\nname: review\nmodel: local\n---\nLocally edited.\n",
        encoding="utf-8",
    )

    emitted: list[object] = []
    _sync_status(emitted.append)

    payload = _single_payload(emitted)
    assert payload == [
        {
            "key": "skills/review",
            "status": "locally-modified",
            "reason": "Local content differs from the lock file.",
            "source_name": "source",
            "item_kind": "skill",
            "dest_path": ".agents/skills/review",
        }
    ]


def test_sync_remove_uninstalls_managed_items(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    source_dir = tmp_path / "source"
    repo_root.mkdir()
    _write_source_skill(source_dir, "review", "Review carefully.\n")
    monkeypatch.chdir(repo_root)

    _sync_install(lambda payload: None, str(source_dir))

    emitted: list[object] = []
    _sync_remove(emitted.append, "source")

    payload = _single_payload(emitted)
    assert payload["removed"] == 1
    assert payload["warned"] == 0
    assert payload["errors"] == []
    assert payload["items"] == [
        {
            "key": "skills/review",
            "action": "removed",
            "reason": "Removed managed item.",
            "dest_path": ".agents/skills/review",
        }
    ]

    assert not (repo_root / ".agents" / "skills" / "review").exists()
    assert not (repo_root / ".claude" / "skills" / "review").exists()
    assert load_sync_config(repo_root / ".meridian" / "config.toml").sources == ()
    assert read_lock_file(repo_root / ".meridian" / "sync.lock").items == {}


def _single_payload(emitted: list[object]) -> object:
    assert len(emitted) == 1
    return emitted[0]


def _write_source_skill(source_dir: Path, name: str, body: str) -> None:
    skill_dir = source_dir / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\nmodel: source-model\n---\n{body}",
        encoding="utf-8",
    )


def _write_source_agent(source_dir: Path, name: str, body: str) -> None:
    agents_dir = source_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.md").write_text(
        f"---\nname: {name}\nmodel: source-model\n---\n{body}",
        encoding="utf-8",
    )

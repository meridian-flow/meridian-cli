from pathlib import Path

from meridian.lib.sync.install_config import ManagedSourceConfig
from meridian.lib.sync.install_engine import reconcile_managed_sources
from meridian.lib.sync.install_lock import ManagedInstallLock


def _write_source_agent(source_dir: Path, name: str, body: str = "hello\n") -> None:
    agents_dir = source_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    (agents_dir / f"{name}.md").write_text(
        f"---\nname: {name}\nmodel: gpt-5.3-codex\n---\n{body}",
        encoding="utf-8",
    )


def test_reconcile_renamed_item_removes_previous_destination(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source_dir = tmp_path / "source"
    _write_source_agent(source_dir, "a")

    lock = ManagedInstallLock()
    initial = ManagedSourceConfig(
        name="demo",
        kind="path",
        path=source_dir.as_posix(),
        rename={"agent:a": "foo"},
    )
    result = reconcile_managed_sources(
        repo_root=repo_root,
        sources=(initial,),
        lock=lock,
        agents_cache_dir=repo_root / ".meridian" / "cache" / "agents",
    )
    assert not result.errors
    assert (repo_root / ".agents" / "agents" / "foo.md").is_file()

    renamed = ManagedSourceConfig(
        name="demo",
        kind="path",
        path=source_dir.as_posix(),
        rename={"agent:a": "bar"},
    )
    result = reconcile_managed_sources(
        repo_root=repo_root,
        sources=(renamed,),
        lock=lock,
        agents_cache_dir=repo_root / ".meridian" / "cache" / "agents",
    )

    assert not result.errors
    assert not (repo_root / ".agents" / "agents" / "foo.md").exists()
    assert (repo_root / ".agents" / "agents" / "bar.md").is_file()
    assert lock.items["agent:a"].destination_path == ".agents/agents/bar.md"


def test_reconcile_renamed_item_keeps_previous_modified_destination(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    source_dir = tmp_path / "source"
    _write_source_agent(source_dir, "a")

    lock = ManagedInstallLock()
    initial = ManagedSourceConfig(
        name="demo",
        kind="path",
        path=source_dir.as_posix(),
        rename={"agent:a": "foo"},
    )
    reconcile_managed_sources(
        repo_root=repo_root,
        sources=(initial,),
        lock=lock,
        agents_cache_dir=repo_root / ".meridian" / "cache" / "agents",
    )

    previous_path = repo_root / ".agents" / "agents" / "foo.md"
    previous_path.write_text(
        "---\nname: a\nmodel: gpt-5.3-codex\n---\nlocal edit\n",
        encoding="utf-8",
    )

    renamed = ManagedSourceConfig(
        name="demo",
        kind="path",
        path=source_dir.as_posix(),
        rename={"agent:a": "bar"},
    )
    result = reconcile_managed_sources(
        repo_root=repo_root,
        sources=(renamed,),
        lock=lock,
        agents_cache_dir=repo_root / ".meridian" / "cache" / "agents",
    )

    assert not result.errors
    assert result.actions[0].action == "kept"
    assert previous_path.is_file()
    assert not (repo_root / ".agents" / "agents" / "bar.md").exists()
    assert lock.items["agent:a"].destination_path == ".agents/agents/foo.md"

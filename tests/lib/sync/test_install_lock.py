from pathlib import Path

import pytest

from meridian.lib.sync.install_lock import LockedInstalledItem, LockedSourceItem, LockedSourceRecord
from meridian.lib.sync.install_lock import ManagedInstallLock, read_install_lock, write_install_lock


def test_write_install_lock_roundtrip(tmp_path: Path) -> None:
    lock_path = tmp_path / ".meridian" / "agents.lock"
    lock = ManagedInstallLock(
        sources={
            "meridian-agents": LockedSourceRecord(
                kind="git",
                locator="https://github.com/haowjy/meridian-agents.git",
                requested_ref="main",
                resolved_identity={"commit": "abc123"},
                items={
                    "agent:__meridian-orchestrator": LockedSourceItem(
                        path="agents/__meridian-orchestrator.md",
                        managed=True,
                        system=True,
                        depends_on=("skill:__meridian-orchestrate",),
                    )
                },
                realized_closure=("agent:__meridian-orchestrator", "skill:__meridian-orchestrate"),
                installed_tree_hash="sha256:1234",
                installed_at="2026-03-14T12:00:00Z",
            )
        },
        items={
            "agent:__meridian-orchestrator": LockedInstalledItem(
                source_name="meridian-agents",
                source_item_id="agent:__meridian-orchestrator",
                destination_path=".agents/agents/__meridian-orchestrator.md",
                content_hash="sha256:1234",
            )
        },
    )

    write_install_lock(lock_path, lock)

    assert read_install_lock(lock_path) == lock


def test_locked_source_item_rejects_noncanonical_dependencies() -> None:
    with pytest.raises(ValueError, match="expected canonical 'agent:name' or 'skill:name'"):
        LockedSourceItem(path="agents/dev-orchestrator.md", depends_on=("dev-orchestrator",))

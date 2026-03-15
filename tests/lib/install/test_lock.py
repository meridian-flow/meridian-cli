from pathlib import Path

from meridian.lib.install.lock import (
    InstallLock,
    LockedInstalledItem,
    LockedSourceItem,
    LockedSourceRecord,
    read_lock,
    write_lock,
)


def test_write_lock_roundtrip(tmp_path: Path) -> None:
    lock_path = tmp_path / ".meridian" / "agents.lock"
    lock = InstallLock(
        sources={
            "meridian-base": LockedSourceRecord(
                kind="git",
                locator="https://github.com/haowjy/meridian-base.git",
                requested_ref="main",
                resolved_identity={"commit": "abc123"},
                items={
                    "agent:__meridian-orchestrator": LockedSourceItem(
                        path="agents/__meridian-orchestrator.md",
                    )
                },
                realized_closure=("agent:__meridian-orchestrator",),
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

    write_lock(lock_path, lock)

    assert read_lock(lock_path) == lock

"""Work attachment helpers shared by launch, spawn, and work flows."""

from __future__ import annotations

from pathlib import Path

from meridian.lib.state import session_store, work_store


def session_exists(state_root: Path, chat_id: str) -> bool:
    normalized = chat_id.strip()
    if not normalized:
        return False
    return session_store.get_session_harness_id(state_root, normalized) is not None


def set_session_work_attachment(
    state_root: Path,
    *,
    chat_id: str,
    work_id: str | None,
) -> bool:
    normalized = chat_id.strip()
    if not session_exists(state_root, normalized):
        return False
    session_store.update_session_work_id(state_root, normalized, work_id)
    return True


def ensure_explicit_work_item(state_root: Path, work_id: str) -> str:
    """Create-or-attach an explicitly named work item and return its slug."""

    return work_store.ensure_work_item_metadata(state_root, work_id).name

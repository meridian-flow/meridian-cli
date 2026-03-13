"""Session policy helpers."""

from __future__ import annotations

from pathlib import Path

import structlog

from meridian.lib.state import work_store
from meridian.lib.state.session_store import get_session_active_work_id, update_session_work_id

logger = structlog.get_logger(__name__)


def ensure_session_work_item(
    state_root: Path,
    chat_id: str,
    *,
    inherited_work_id: str | None = None,
) -> str:
    existing_work_id = get_session_active_work_id(state_root, chat_id)
    if existing_work_id:
        return existing_work_id

    # Inherit parent's work item instead of creating a new auto one.
    resolved_inherited = (inherited_work_id or "").strip()
    if resolved_inherited:
        item = work_store.get_work_item(state_root, resolved_inherited)
        if item is not None:
            update_session_work_id(state_root, chat_id, resolved_inherited)
            return resolved_inherited
        logger.warning(
            "Inherited work item not found, creating auto work item.",
            inherited_work_id=resolved_inherited,
            chat_id=chat_id,
        )

    auto_item = work_store.create_auto_work_item(state_root)
    update_session_work_id(state_root, chat_id, auto_item.name)
    return auto_item.name


__all__ = ["ensure_session_work_item"]

"""Shared session-detection helpers that stay harness-agnostic."""

from pathlib import Path


def infer_harness_from_untracked_session_ref(repo_root: Path, session_ref: str) -> str | None:
    """Detect which harness owns *session_ref* by querying registered adapters."""

    normalized = session_ref.strip()
    if not normalized:
        return None

    from meridian.lib.harness.registry import get_default_harness_registry

    registry = get_default_harness_registry()
    for harness_id in registry.ids():
        adapter = registry.get(harness_id)
        if adapter.owns_untracked_session(repo_root=repo_root, session_ref=normalized):
            return str(harness_id)
    return None

"""Shared session-detection helpers that stay harness-agnostic."""

from pathlib import Path

from meridian.lib.harness.ids import HarnessId
from meridian.lib.harness.registry import HarnessRegistry, get_default_harness_registry


def infer_harness_from_untracked_session_ref(
    repo_root: Path,
    session_ref: str,
    *,
    registry: HarnessRegistry | None = None,
) -> HarnessId | None:
    """Detect which harness owns *session_ref* by querying registered adapters."""

    normalized = session_ref.strip()
    if not normalized:
        return None

    active_registry = registry if registry is not None else get_default_harness_registry()
    for harness_id in active_registry.ids():
        try:
            adapter = active_registry.get_subprocess_harness(harness_id)
        except TypeError:
            continue
        if adapter.owns_untracked_session(repo_root=repo_root, session_ref=normalized):
            return harness_id
    return None

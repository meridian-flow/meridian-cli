"""Shared session/spawn reference resolution helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.harness.session_detection import infer_harness_from_untracked_session_ref
from meridian.lib.ops.runtime import resolve_state_root
from meridian.lib.state import session_store, spawn_store
from meridian.lib.state.paths import resolve_spawn_log_dir

_SPAWN_REF_RE = re.compile(r"^p\d+$")
_CHAT_REF_RE = re.compile(r"^c\d+$")


@dataclass(frozen=True)
class ResolvedSessionReference:
    """Result of resolving a user-provided session/spawn reference."""

    harness_session_id: str | None
    harness: str | None
    source_chat_id: str | None
    source_model: str | None
    source_agent: str | None
    source_skills: tuple[str, ...]
    source_work_id: str | None
    tracked: bool
    source_execution_cwd: str | None = None
    warning: str | None = None

    @property
    def missing_harness_session_id(self) -> bool:
        """True when a tracked reference exists but has no recorded harness session id."""

        return self.tracked and self.harness_session_id is None


def _normalize_optional(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _latest_harness_session_id(record: session_store.SessionRecord) -> str | None:
    for candidate in reversed(record.harness_session_ids):
        normalized = candidate.strip()
        if normalized:
            return normalized
    return _normalize_optional(record.harness_session_id)


def _resolve_untracked_reference(repo_root: Path, ref: str) -> ResolvedSessionReference:
    registry = get_default_harness_registry()
    inferred_harness = infer_harness_from_untracked_session_ref(
        repo_root,
        ref,
        registry=registry,
    )
    return ResolvedSessionReference(
        harness_session_id=ref,
        harness=str(inferred_harness) if inferred_harness is not None else None,
        source_chat_id=None,
        source_model=None,
        source_agent=None,
        source_skills=(),
        source_work_id=None,
        tracked=False,
        warning=(
            f"Session '{ref}' is not tracked yet; "
            "resuming with the provided harness session id."
        ),
    )


def _build_tracked_reference(
    *,
    harness_session_id: str | None,
    stored_harness: str | None,
    source_chat_id: str | None,
    source_model: str | None,
    source_agent: str | None,
    source_skills: tuple[str, ...],
    source_work_id: str | None,
    source_execution_cwd: str | None = None,
    repo_root: Path,
) -> ResolvedSessionReference:
    registry = get_default_harness_registry()
    verified_harness = (
        infer_harness_from_untracked_session_ref(
            repo_root,
            harness_session_id,
            registry=registry,
        )
        if harness_session_id is not None
        else None
    )
    return ResolvedSessionReference(
        harness_session_id=harness_session_id,
        harness=str(verified_harness) if verified_harness is not None else stored_harness,
        source_chat_id=source_chat_id,
        source_model=source_model,
        source_agent=source_agent,
        source_skills=source_skills,
        source_work_id=source_work_id,
        source_execution_cwd=source_execution_cwd,
        tracked=True,
    )


def _resolve_spawn_reference(
    state_root: Path, ref: str, repo_root: Path
) -> ResolvedSessionReference:
    row = spawn_store.get_spawn(state_root, ref)
    if row is None:
        return _resolve_untracked_reference(repo_root, ref)

    harness_session_id = _normalize_optional(row.harness_session_id)
    stored_harness = _normalize_optional(row.harness)
    source_execution_cwd = row.execution_cwd
    if source_execution_cwd is None and row.harness == "claude" and row.kind == "child":
        # Legacy Claude child spawns executed from the spawn log directory.
        source_execution_cwd = str(resolve_spawn_log_dir(repo_root, ref))
    elif source_execution_cwd is None:
        source_execution_cwd = str(repo_root)
    return _build_tracked_reference(
        harness_session_id=harness_session_id,
        stored_harness=stored_harness,
        source_chat_id=_normalize_optional(row.chat_id),
        source_model=_normalize_optional(row.model),
        source_agent=_normalize_optional(row.agent),
        source_skills=row.skills,
        source_work_id=_normalize_optional(row.work_id),
        source_execution_cwd=source_execution_cwd,
        repo_root=repo_root,
    )


def _resolve_chat_reference(
    state_root: Path, ref: str, repo_root: Path
) -> ResolvedSessionReference:
    records = session_store.get_session_records(state_root, {ref})
    if not records:
        return _resolve_untracked_reference(repo_root, ref)

    session = records[0]
    harness_session_id = _latest_harness_session_id(session)
    stored_harness = _normalize_optional(session.harness)
    return _build_tracked_reference(
        harness_session_id=harness_session_id,
        stored_harness=stored_harness,
        source_chat_id=session.chat_id,
        source_model=_normalize_optional(session.model),
        source_agent=_normalize_optional(session.agent),
        source_skills=session.skills,
        source_work_id=_normalize_optional(session.active_work_id),
        source_execution_cwd=session.execution_cwd or str(repo_root),
        repo_root=repo_root,
    )


def _resolve_harness_session_reference(
    state_root: Path, ref: str, repo_root: Path
) -> ResolvedSessionReference:
    session = session_store.resolve_session_ref(state_root, ref)
    if session is None:
        return _resolve_untracked_reference(repo_root, ref)

    stored_harness_session_id = _normalize_optional(session.harness_session_id)
    harness_session_id = stored_harness_session_id or ref
    stored_harness = _normalize_optional(session.harness)
    return _build_tracked_reference(
        harness_session_id=harness_session_id,
        stored_harness=stored_harness,
        source_chat_id=session.chat_id,
        source_model=_normalize_optional(session.model),
        source_agent=_normalize_optional(session.agent),
        source_skills=session.skills,
        source_work_id=_normalize_optional(session.active_work_id),
        source_execution_cwd=session.execution_cwd or str(repo_root),
        repo_root=repo_root,
    )


def resolve_session_reference(repo_root: Path, ref: str) -> ResolvedSessionReference:
    """Resolve a session/spawn reference to harness session ID and source metadata."""

    normalized = ref.strip()
    if not normalized:
        raise ValueError("Session reference is required.")

    state_root = resolve_state_root(repo_root)
    if _SPAWN_REF_RE.fullmatch(normalized):
        return _resolve_spawn_reference(state_root, normalized, repo_root)
    if _CHAT_REF_RE.fullmatch(normalized):
        return _resolve_chat_reference(state_root, normalized, repo_root)
    return _resolve_harness_session_reference(state_root, normalized, repo_root)


__all__ = [
    "ResolvedSessionReference",
    "resolve_session_reference",
]

"""Codex harness extractor."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from meridian.lib.core.domain import TokenUsage
from meridian.lib.core.types import SpawnId
from meridian.lib.harness.adapter import ArtifactStore
from meridian.lib.harness.common import (
    extract_codex_report,
    extract_session_id_from_artifacts_with_patterns,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.connections.base import HarnessEvent
from meridian.lib.harness.launch_spec import CodexLaunchSpec
from meridian.lib.platform import get_home_path

from .base import HarnessExtractor, session_from_mapping_with_keys

_SESSION_ID_TEXT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcodex\s+resume\s+([A-Za-z0-9][A-Za-z0-9._:-]{5,})\b", re.IGNORECASE),
    re.compile(r"\bresume\s+([A-Za-z0-9][A-Za-z0-9._:-]{5,})\b", re.IGNORECASE),
)
_ROLLOUT_FILENAME_RE = re.compile(
    r"^rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-(?P<session_id>[0-9a-fA-F-]{36})\.jsonl$"
)


def _resolve_rollout_session_id(path: Path, repo_root: Path) -> str | None:
    session_id: str | None = None
    saw_assistant_message = False
    saw_turn_aborted = False

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return None

    for line in lines:
        try:
            payload_obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload_obj, dict):
            continue
        payload = cast("dict[str, object]", payload_obj)
        payload_type = payload.get("type")
        if not isinstance(payload_type, str):
            continue

        if payload_type == "session_meta":
            raw_meta = payload.get("payload")
            if not isinstance(raw_meta, dict):
                continue
            meta = cast("dict[str, object]", raw_meta)
            candidate_session_id = meta.get("id")
            cwd = meta.get("cwd")
            if not isinstance(candidate_session_id, str) or not candidate_session_id.strip():
                continue
            if not isinstance(cwd, str):
                continue
            try:
                if Path(cwd).expanduser().resolve() != repo_root:
                    return None
            except OSError:
                continue
            session_id = candidate_session_id.strip()
            continue

        if payload_type == "response_item":
            raw_item = payload.get("payload")
            if not isinstance(raw_item, dict):
                continue
            item = cast("dict[str, object]", raw_item)
            if item.get("type") == "message" and item.get("role") == "assistant":
                saw_assistant_message = True
            continue

        if payload_type == "event_msg":
            raw_event = payload.get("payload")
            if isinstance(raw_event, dict):
                event_payload = cast("dict[str, object]", raw_event)
                if event_payload.get("type") == "turn_aborted":
                    saw_turn_aborted = True
            continue

        if payload_type == "turn_aborted":
            saw_turn_aborted = True

    if session_id is None:
        return None
    if saw_turn_aborted and not saw_assistant_message:
        return None
    return session_id


def _detect_primary_session_id(
    *,
    child_cwd: Path,
    launch_env: Mapping[str, str],
) -> str | None:
    codex_home = launch_env.get("CODEX_HOME", "").strip()
    home = launch_env.get("HOME", "").strip()
    if codex_home:
        sessions_root = Path(codex_home).expanduser() / "sessions"
    elif home:
        sessions_root = Path(home).expanduser() / ".codex" / "sessions"
    else:
        sessions_root = get_home_path() / ".codex" / "sessions"

    if not sessions_root.is_dir():
        return None

    repo_root = child_cwd.resolve()
    candidates: list[tuple[float, Path]] = []
    for candidate in sessions_root.rglob("rollout-*.jsonl"):
        if _ROLLOUT_FILENAME_RE.match(candidate.name) is None:
            continue
        try:
            modified_at = candidate.stat().st_mtime
        except OSError:
            continue
        candidates.append((modified_at, candidate))

    for _, candidate in sorted(candidates, key=lambda item: item[0], reverse=True):
        resolved = _resolve_rollout_session_id(candidate, repo_root)
        if resolved:
            return resolved
    return None


class CodexHarnessExtractor(HarnessExtractor[CodexLaunchSpec]):
    """Extractor implementation for Codex artifacts and events."""

    def detect_session_id_from_event(self, event: HarnessEvent) -> str | None:
        return session_from_mapping_with_keys(
            event.payload,
            (
                "threadId",
                "thread_id",
                "session_id",
                "sessionId",
                "sessionID",
                "conversation_id",
                "conversationId",
            ),
        )

    def detect_session_id_from_artifacts(
        self,
        *,
        spec: CodexLaunchSpec,
        launch_env: Mapping[str, str],
        child_cwd: Path,
        state_root: Path,
    ) -> str | None:
        _ = state_root
        if spec.continue_session_id and spec.continue_session_id.strip():
            return spec.continue_session_id.strip()
        return _detect_primary_session_id(child_cwd=child_cwd, launch_env=launch_env)

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts_with_patterns(
            artifacts,
            spawn_id,
            json_keys=(
                "session_id",
                "sessionId",
                "sessionID",
                "conversation_id",
                "conversationId",
                "thread_id",
                "threadId",
            ),
            text_patterns=_SESSION_ID_TEXT_PATTERNS,
        )

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_codex_report(artifacts, spawn_id)


CODEX_EXTRACTOR = CodexHarnessExtractor()

__all__ = ["CODEX_EXTRACTOR", "CodexHarnessExtractor"]

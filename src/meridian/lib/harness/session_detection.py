"""Shared session-detection helpers for harness adapters.

Centralises harness-specific path knowledge (codex rollout files, opencode
log files) so that both launch.py and cli/main.py can reuse the same logic
without duplicating regex patterns or filesystem heuristics.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

CODEX_ROLLOUT_FILENAME_RE = re.compile(
    r"^rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-(?P<session_id>[0-9a-fA-F-]{36})\.jsonl$"
)
OPENCODE_SESSION_CREATED_RE = re.compile(
    r"^\w+\s+(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s+\+\d+ms\s+"
    r"service=session\s+id=(?P<session_id>\S+)\s+.*?\bdirectory=(?P<directory>\S+)\b.*\bcreated\b"
)


def resolve_codex_rollout_session_id(path: Path, resolved_repo: Path) -> str | None:
    """Parse a single codex rollout JSONL file and return the session ID if it
    belongs to *resolved_repo* and is not an aborted bootstrap."""

    session_id: str | None = None
    saw_assistant_message = False
    saw_turn_aborted = False

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            try:
                payload_obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload_obj, dict):
                continue
            payload_type = payload_obj.get("type")

            if payload_type == "session_meta":
                payload = payload_obj.get("payload")
                if not isinstance(payload, dict):
                    continue
                candidate_session_id = payload.get("id")
                cwd = payload.get("cwd")
                if not isinstance(candidate_session_id, str) or not candidate_session_id.strip():
                    continue
                if not isinstance(cwd, str):
                    continue
                try:
                    cwd_matches = Path(cwd).expanduser().resolve() == resolved_repo
                except OSError:
                    continue
                if not cwd_matches:
                    return None
                session_id = candidate_session_id.strip()
                continue

            if payload_type == "response_item":
                payload = payload_obj.get("payload")
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") == "message" and payload.get("role") == "assistant":
                    saw_assistant_message = True
                continue

            if payload_type == "event_msg":
                payload = payload_obj.get("payload")
                if isinstance(payload, dict) and payload.get("type") == "turn_aborted":
                    saw_turn_aborted = True
                continue

            if payload_type == "turn_aborted":
                saw_turn_aborted = True

    if session_id is None:
        return None
    if saw_turn_aborted and not saw_assistant_message:
        return None
    return session_id


def resolve_codex_primary_session_id(repo_root: Path, started_at_epoch: float) -> str | None:
    """Scan codex rollout files for the most recent session matching *repo_root*."""

    sessions_root = Path.home() / ".codex" / "sessions"
    if not sessions_root.is_dir():
        return None

    resolved_repo = repo_root.resolve()
    candidates: list[tuple[float, Path]] = []
    for candidate in sessions_root.rglob("rollout-*.jsonl"):
        match = CODEX_ROLLOUT_FILENAME_RE.match(candidate.name)
        if match is None:
            continue
        try:
            modified_at = candidate.stat().st_mtime
        except OSError:
            continue
        if modified_at + 1 < started_at_epoch:
            continue
        candidates.append((modified_at, candidate))

    for _, path in sorted(candidates, key=lambda item: item[0], reverse=True):
        try:
            resolved = resolve_codex_rollout_session_id(path, resolved_repo)
        except OSError:
            logger.debug("Failed to read codex rollout %s", path, exc_info=True)
            continue
        if resolved is not None:
            return resolved
    return None


def resolve_opencode_primary_session_id(
    repo_root: Path,
    started_at_epoch: float,
    started_at_local_iso: str,
) -> str | None:
    """Scan opencode log files for the most recent session matching *repo_root*."""

    logs_root = Path.home() / ".local" / "share" / "opencode" / "log"
    if not logs_root.is_dir():
        return None

    resolved_repo = repo_root.resolve()
    matches: list[tuple[str, str]] = []
    for candidate in logs_root.glob("*.log"):
        try:
            modified_at = candidate.stat().st_mtime
        except OSError:
            continue
        if modified_at + 1 < started_at_epoch:
            continue
        try:
            lines = candidate.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            logger.debug("Failed to read opencode log %s", candidate, exc_info=True)
            continue
        for line in lines:
            match = OPENCODE_SESSION_CREATED_RE.match(line)
            if match is None:
                continue
            timestamp = match.group("ts")
            if timestamp < started_at_local_iso:
                continue
            directory = match.group("directory")
            if Path(directory).expanduser().resolve() != resolved_repo:
                continue
            session_id = match.group("session_id").strip()
            if session_id:
                matches.append((timestamp, session_id))

    if not matches:
        return None
    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def detect_primary_harness_session_id(
    *,
    harness_id: str,
    repo_root: Path,
    started_at_epoch: float,
    started_at_local_iso: str | None = None,
) -> str | None:
    """Detect the harness-native session ID for a completed primary launch."""

    normalized_harness = harness_id.strip().lower()
    if normalized_harness == "codex":
        return resolve_codex_primary_session_id(repo_root, started_at_epoch)
    if normalized_harness != "opencode":
        return None

    local_iso = (
        started_at_local_iso
        if started_at_local_iso is not None
        else datetime.fromtimestamp(started_at_epoch).strftime("%Y-%m-%dT%H:%M:%S")
    )
    return resolve_opencode_primary_session_id(repo_root, started_at_epoch, local_iso)


def infer_harness_from_untracked_session_ref(repo_root: Path, session_ref: str) -> str | None:
    """Guess which harness owns *session_ref* by checking codex rollout files
    and opencode log files on disk."""

    normalized = session_ref.strip()
    if not normalized:
        return None

    resolved_repo = repo_root.resolve()

    codex_root = Path.home() / ".codex" / "sessions"
    if codex_root.is_dir():
        for candidate in codex_root.rglob(f"rollout-*-{normalized}.jsonl"):
            if CODEX_ROLLOUT_FILENAME_RE.match(candidate.name) is None:
                continue
            try:
                with candidate.open("r", encoding="utf-8", errors="ignore") as handle:
                    for _ in range(5):
                        line = handle.readline()
                        if not line:
                            break
                        payload_obj = json.loads(line)
                        if not isinstance(payload_obj, dict):
                            continue
                        if payload_obj.get("type") != "session_meta":
                            continue
                        payload = payload_obj.get("payload")
                        if not isinstance(payload, dict):
                            continue
                        session_id = payload.get("id")
                        cwd = payload.get("cwd")
                        if not isinstance(session_id, str) or session_id.strip() != normalized:
                            continue
                        if not isinstance(cwd, str):
                            continue
                        try:
                            cwd_matches = Path(cwd).expanduser().resolve() == resolved_repo
                        except OSError:
                            continue
                        if cwd_matches:
                            return "codex"
            except (OSError, json.JSONDecodeError):
                continue

    opencode_logs = Path.home() / ".local" / "share" / "opencode" / "log"
    if opencode_logs.is_dir():
        for candidate in opencode_logs.glob("*.log"):
            try:
                lines = candidate.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for line in lines:
                match = OPENCODE_SESSION_CREATED_RE.match(line)
                if match is None:
                    continue
                if match.group("session_id").strip() != normalized:
                    continue
                directory = match.group("directory")
                try:
                    directory_matches = Path(directory).expanduser().resolve() == resolved_repo
                except OSError:
                    continue
                if directory_matches:
                    return "opencode"

    return None

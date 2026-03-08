"""File-touch extraction helpers from harness output artifacts."""

from __future__ import annotations

import json
import re
from typing import cast

from meridian.lib.extract._io import read_artifact_text
from meridian.lib.state.artifact_store import ArtifactStore
from meridian.lib.types import SpawnId

_PATH_KEYS: frozenset[str] = frozenset(
    {
        "path",
        "file",
        "file_path",
        "filepath",
        "source",
        "target",
    }
)
_FILE_LIST_KEYS: frozenset[str] = frozenset(
    {
        "files",
        "files_touched",
        "touched_files",
        "modified_files",
        "paths",
    }
)
_PATH_PATTERN = re.compile(
    r"(?<![\w/.-])(?:[A-Za-z]:\\)?(?:\.{1,2}/)?(?:[\w.-]+[\\/])+[\w.-]+(?:\.[\w.-]+)?"
)
_KNOWN_DIR_PREFIXES: tuple[str, ...] = (
    "src/",
    "tests/",
    "docs/",
    "_docs/",
    "plans/",
    "backlog/",
    "frontend/",
    "backend/",
    "scripts/",
    ".agents/",
    ".meridian/",
    "config/",
)


def _strip_relative_prefixes(path: str) -> str:
    normalized = path
    while normalized.startswith("./"):
        normalized = normalized[2:]
    while normalized.startswith("../"):
        normalized = normalized[3:]
    return normalized


def _has_file_extension(path: str) -> bool:
    filename = path.rsplit("/", 1)[-1]
    if not filename:
        return False
    return "." in filename and not filename.endswith(".")


def _normalize_path(value: str) -> str | None:
    candidate = value.strip().strip("`'\"()[]{}<>.,:;")
    if not candidate:
        return None
    if "://" in candidate:
        return None
    normalized = candidate.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    if "/" not in normalized:
        return None
    candidate = _strip_relative_prefixes(normalized)
    if not (
        _has_file_extension(candidate)
        or any(candidate.startswith(prefix) for prefix in _KNOWN_DIR_PREFIXES)
    ):
        return None
    return normalized


def _append_path(found: list[str], seen: set[str], candidate: str) -> None:
    normalized = _normalize_path(candidate)
    if normalized is None or normalized in seen:
        return
    seen.add(normalized)
    found.append(normalized)


def _extract_paths_from_text(text: str) -> list[str]:
    return [match.group(0) for match in _PATH_PATTERN.finditer(text)]


def _extract_from_json_value(value: object, found: list[str], seen: set[str]) -> None:
    if isinstance(value, dict):
        payload = cast("dict[str, object]", value)
        for key, nested in payload.items():
            key_lower = key.lower()
            if key_lower in _PATH_KEYS and isinstance(nested, str):
                _append_path(found, seen, nested)
                continue
            if key_lower in _FILE_LIST_KEYS and isinstance(nested, list):
                for item in cast("list[object]", nested):
                    if isinstance(item, str):
                        _append_path(found, seen, item)
                    else:
                        _extract_from_json_value(item, found, seen)
                continue
            if isinstance(nested, str):
                for candidate in _extract_paths_from_text(nested):
                    _append_path(found, seen, candidate)
            else:
                _extract_from_json_value(nested, found, seen)
        return

    if isinstance(value, list):
        for nested in cast("list[object]", value):
            _extract_from_json_value(nested, found, seen)
        return

    if isinstance(value, str):
        for candidate in _extract_paths_from_text(value):
            _append_path(found, seen, candidate)


def extract_files_touched(artifacts: ArtifactStore, spawn_id: SpawnId) -> tuple[str, ...]:
    """Extract touched file paths from explicit and inferred artifact content."""

    found: list[str] = []
    seen: set[str] = set()

    explicit_json = read_artifact_text(artifacts, spawn_id, "files_touched.json").strip()
    if explicit_json:
        try:
            payload_obj = json.loads(explicit_json)
        except json.JSONDecodeError:
            payload_obj = None
        if payload_obj is not None:
            _extract_from_json_value(payload_obj, found, seen)

    explicit_text = read_artifact_text(artifacts, spawn_id, "files_touched.txt")
    for line in explicit_text.splitlines():
        _append_path(found, seen, line)

    output_lines = read_artifact_text(artifacts, spawn_id, "output.jsonl")
    for line in output_lines.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload_obj = json.loads(stripped)
        except json.JSONDecodeError:
            payload_obj = None
        if payload_obj is not None:
            _extract_from_json_value(payload_obj, found, seen)
            continue

        for candidate in _extract_paths_from_text(stripped):
            _append_path(found, seen, candidate)

    report = read_artifact_text(artifacts, spawn_id, "report.md")
    for candidate in _extract_paths_from_text(report):
        _append_path(found, seen, candidate)

    return tuple(found)

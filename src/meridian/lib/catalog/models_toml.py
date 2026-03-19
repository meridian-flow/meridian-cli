"""Filesystem helpers for `.meridian/models.toml`."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import cast

from meridian.lib.catalog.model_policy import DEFAULT_HARNESS_PATTERNS, DEFAULT_MODEL_VISIBILITY
from meridian.lib.core.types import HarnessId
from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.paths import resolve_state_paths


def catalog_path(repo_root: Path) -> Path:
    return resolve_state_paths(repo_root).models_path


def load_models_file_payload(path: Path) -> dict[str, object]:
    payload_obj = tomllib.loads(path.read_text(encoding="utf-8"))
    return cast("dict[str, object]", payload_obj)


def ensure_models_config(repo_root: Path) -> Path:
    """Scaffold `.meridian/models.toml` with commented defaults when missing."""

    path = catalog_path(repo_root)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, scaffold_models_toml())
    return path


def scaffold_models_toml() -> str:
    """Return commented defaults for `.meridian/models.toml`."""

    lines = [
        "# Model catalog overrides.",
        "# Uncomment and edit the sections below to customize models, routing, and visibility.",
        "",
        "# [models]",
        '# opus = "claude-opus-4-6"            # pinned alias shorthand',
        "",
        "# [models.fast]                        # auto-resolve: picks latest match",
        '# provider = "google"',
        '# include = "flash"',
        '# exclude = ["-lite"]',
        '# description = "Quick model for simple tasks."',
        "",
        '# [models."gpt-5.4-mini"]              # key is model ID when no model_id field',
        '# description = "Quick and cheap for simple tasks."',
        '# pinned = true                         # always show regardless of filters',
        "",
        "# [harness_patterns]",
        f"# claude = {_toml_literal(DEFAULT_HARNESS_PATTERNS[HarnessId.CLAUDE])}",
        f"# codex = {_toml_literal(DEFAULT_HARNESS_PATTERNS[HarnessId.CODEX])}",
        f"# opencode = {_toml_literal(DEFAULT_HARNESS_PATTERNS[HarnessId.OPENCODE])}",
        "",
        "# [model_visibility]",
        "# include = []",
        f"# exclude = {_toml_literal(DEFAULT_MODEL_VISIBILITY.exclude)}",
        f"# hide_date_variants = {_toml_literal(DEFAULT_MODEL_VISIBILITY.hide_date_variants)}",
        f"# hide_superseded = {_toml_literal(DEFAULT_MODEL_VISIBILITY.hide_superseded)}",
        f"# max_age_days = {_toml_literal(DEFAULT_MODEL_VISIBILITY.max_age_days)}",
        f"# max_input_cost = {_toml_literal(DEFAULT_MODEL_VISIBILITY.max_input_cost)}",
        "",
    ]
    return "\n".join(lines)


def render_models_toml(payload: dict[str, object]) -> str:
    """Render normalized `.meridian/models.toml` content."""

    lines: list[str] = []

    models = payload.get("models")
    if isinstance(models, dict) and models:
        # Separate top-level string entries from sub-table entries
        string_entries: dict[str, str] = {}
        table_entries: dict[str, dict[str, object]] = {}

        models_dict = cast("dict[str, object]", models)
        for key in sorted(models_dict):
            value = models_dict[key]
            if isinstance(value, str):
                string_entries[key] = value
            elif isinstance(value, dict):
                table_entries[key] = cast("dict[str, object]", value)

        if string_entries:
            lines.append("[models]")
            for key in sorted(string_entries):
                lines.append(f"{json.dumps(key)} = {_toml_literal(string_entries[key])}")

        for key in sorted(table_entries):
            entry = table_entries[key]
            if not entry:
                continue
            if lines:
                lines.append("")
            lines.append(f"[models.{json.dumps(key)}]")
            for field in sorted(entry):
                lines.append(f"{field} = {_toml_literal(entry[field])}")

    harness_patterns = payload.get("harness_patterns")
    if isinstance(harness_patterns, dict) and harness_patterns:
        if lines:
            lines.append("")
        lines.append("[harness_patterns]")
        patterns_dict = cast("dict[str, object]", harness_patterns)
        for harness in sorted(patterns_dict):
            lines.append(f"{harness} = {_toml_literal(patterns_dict[harness])}")

    model_visibility = payload.get("model_visibility")
    if isinstance(model_visibility, dict) and model_visibility:
        if lines:
            lines.append("")
        lines.append("[model_visibility]")
        visibility_dict = cast("dict[str, object]", model_visibility)
        for key in sorted(visibility_dict):
            lines.append(f"{key} = {_toml_literal(visibility_dict[key])}")

    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _toml_string(value: str) -> str:
    return json.dumps(value)


def _toml_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, tuple | list):
        items = cast("tuple[object, ...] | list[object]", value)
        return "[" + ", ".join(_toml_literal(item) for item in items) + "]"
    raise ValueError(f"Unsupported models.toml value type: {type(value).__name__}")

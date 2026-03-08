"""Reference-file loading and template substitution helpers."""


import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.state.paths import resolve_space_dir
from meridian.lib.core.types import SpaceId

_TEMPLATE_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class TemplateVariableError(ValueError):
    """Template substitution failed due to undefined or malformed variables."""


class ReferenceFile(BaseModel):
    """One reference file loaded from `-f` flags."""

    model_config = ConfigDict(frozen=True)

    path: Path
    content: str


def parse_template_assignments(assignments: Sequence[str]) -> dict[str, str]:
    """Parse CLI template vars passed as `KEY=VALUE`."""

    parsed: dict[str, str] = {}
    for assignment in assignments:
        key, separator, value = assignment.partition("=")
        normalized_key = key.strip()
        if not separator or not normalized_key:
            raise ValueError(
                "Invalid template variable assignment. Expected KEY=VALUE, "
                f"got '{assignment}'."
            )
        parsed[normalized_key] = value
    return parsed


def resolve_template_variables(
    variables: Mapping[str, str | Path],
    *,
    base_dir: Path | None = None,
) -> dict[str, str]:
    """Resolve template variable values (`@path`/Path -> file contents, else literal)."""

    root = (base_dir or Path.cwd()).resolve()
    resolved: dict[str, str] = {}
    for raw_key, raw_value in variables.items():
        key = raw_key.strip()
        if not key:
            raise ValueError("Template variable names must not be empty.")

        value: str | None = None
        path_candidate: Path | None = None
        if isinstance(raw_value, Path):
            path_candidate = raw_value
        else:
            candidate_text = raw_value
            if candidate_text.startswith("@"):
                path_candidate = Path(candidate_text[1:])
            else:
                value = candidate_text

        if path_candidate is not None:
            expanded = path_candidate.expanduser()
            resolved_path = (expanded if expanded.is_absolute() else root / expanded).resolve()
            if not resolved_path.is_file():
                raise FileNotFoundError(
                    f"Template variable '{key}' points to missing file: {resolved_path}"
                )
            value = resolved_path.read_text(encoding="utf-8")

        assert value is not None
        resolved[key] = value
    return resolved


def substitute_template_variables(
    text: str,
    variables: Mapping[str, str],
    *,
    strict: bool = True,
) -> str:
    """Substitute `{{KEY}}` placeholders.

    In strict mode, undefined variables raise `TemplateVariableError`.
    In non-strict mode, undefined placeholders are preserved as-is.
    """

    if strict:
        missing = sorted(
            {
                match.group(1)
                for match in _TEMPLATE_VAR_RE.finditer(text)
                if match.group(1) not in variables
            }
        )
        if missing:
            joined = ", ".join(missing)
            raise TemplateVariableError(f"Undefined template variables: {joined}")

    return _TEMPLATE_VAR_RE.sub(
        lambda match: variables.get(match.group(1), match.group(0)),
        text,
    )


def load_reference_files(
    file_paths: Sequence[str | Path],
    *,
    base_dir: Path | None = None,
    include_content: bool = True,
    space_id: str | None = None,
) -> tuple[ReferenceFile, ...]:
    """Load referenced files in input order."""

    root = (base_dir or Path.cwd()).resolve()
    loaded: list[ReferenceFile] = []
    for raw_path in file_paths:
        if isinstance(raw_path, str) and raw_path.startswith("@"):
            normalized_space_id = (space_id or "").strip()
            if not normalized_space_id:
                raise ValueError(
                    "Space reference requires space context. "
                    "Pass --space before using '-f @name'."
                )
            space_fs_dir = resolve_space_dir(root, SpaceId(normalized_space_id)) / "fs"
            relative = raw_path[1:]
            if not relative:
                raise ValueError("Reference path after '@' must not be empty.")
            resolved = (space_fs_dir / relative).resolve()
        else:
            path_obj = raw_path if isinstance(raw_path, Path) else Path(raw_path)
            expanded = path_obj.expanduser()
            resolved = (expanded if expanded.is_absolute() else root / expanded).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Reference file not found: {resolved}")
        content = resolved.read_text(encoding="utf-8") if include_content else ""
        loaded.append(ReferenceFile(path=resolved, content=content))
    return tuple(loaded)


def render_reference_blocks(references: Sequence[ReferenceFile]) -> tuple[str, ...]:
    """Render loaded references as isolated prompt sections."""

    blocks: list[str] = []
    for reference in references:
        body = reference.content.strip()
        if not body:
            continue
        blocks.append(f"# Reference: {reference.path}\n\n{body}")
    return tuple(blocks)


def render_reference_paths_section(references: Sequence[ReferenceFile]) -> tuple[str, ...]:
    """Render reference paths without inlining file bodies."""

    if not references:
        return ()
    lines = [
        "# Reference Files",
        "",
        "Read these files from disk when gathering context:",
        "",
    ]
    for reference in references:
        lines.append(f"- {reference.path}")
    return ("\n".join(lines),)


__all__ = [
    "ReferenceFile",
    "TemplateVariableError",
    "load_reference_files",
    "parse_template_assignments",
    "render_reference_blocks",
    "render_reference_paths_section",
    "resolve_template_variables",
    "substitute_template_variables",
]

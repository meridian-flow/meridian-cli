"""Mermaid fill-without-color style check."""

from __future__ import annotations

import re

from meridian.lib.mermaid.scanner import DiagramTarget
from meridian.lib.mermaid.style.line_map import content_line_to_file_line
from meridian.lib.mermaid.style.types import StyleWarning, WarningCategory

FILL_NO_COLOR_CATEGORY = WarningCategory(
    id="fill-no-color",
    description="Fill without explicit text color",
    default=True,
    diagram_types=None,
)

_STYLE_FILL_RE = re.compile(r"^\s*style\s+(\S+)\s+.*fill:")
_QUOTED_RE = re.compile(r"(['\"])(?:\\.|(?!\1).)*\1")


def check_fill_no_color(target: DiagramTarget, diagram_type: str | None) -> list[StyleWarning]:
    """Warn on inline style fill declarations without explicit text color."""
    del diagram_type
    warnings: list[StyleWarning] = []
    in_init = False

    for content_line, raw_line in enumerate(target.content.split("\n"), start=1):
        line = raw_line.rstrip("\r")
        stripped = line.strip()

        if in_init:
            if stripped.endswith("}%%"):
                in_init = False
            continue
        if stripped.startswith("%%{init:"):
            if not stripped.endswith("}%%"):
                in_init = True
            continue
        if stripped.startswith("%%"):
            continue

        line_without_quotes = _QUOTED_RE.sub("", line)
        match = _STYLE_FILL_RE.search(line_without_quotes)
        if match is None or "color:" in line_without_quotes:
            continue

        node_id = match.group(1)
        warnings.append(
            StyleWarning(
                category=FILL_NO_COLOR_CATEGORY.id,
                file=target.rel,
                line=content_line_to_file_line(target, content_line),
                message=(
                    f"`style {node_id} fill:#...` without `color:` — "
                    "text may be unreadable across light/dark themes"
                ),
                severity="warning",
                suppressed=False,
                suppression_source=None,
            )
        )

    return warnings


__all__ = ["FILL_NO_COLOR_CATEGORY", "check_fill_no_color"]

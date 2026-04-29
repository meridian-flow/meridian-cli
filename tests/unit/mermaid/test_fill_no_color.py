"""Tests for Mermaid fill-no-color style check."""

from __future__ import annotations

from pathlib import Path

from meridian.lib.mermaid.scanner import DiagramTarget
from meridian.lib.mermaid.style.fill_no_color import check_fill_no_color


def _target(content: str) -> DiagramTarget:
    return DiagramTarget(Path("/tmp/design.md"), "design.md", content, 1, "standalone")


def test_style_fill_without_color_triggers_warning() -> None:
    warnings = check_fill_no_color(_target("graph TD\nstyle NodeA fill:#abc"), "flowchart")
    assert len(warnings) == 1


def test_style_fill_with_color_does_not_trigger() -> None:
    assert (
        check_fill_no_color(_target("graph TD\nstyle NodeA fill:#abc,color:#000"), "flowchart")
        == []
    )


def test_style_without_fill_does_not_trigger() -> None:
    assert check_fill_no_color(_target("graph TD\nstyle NodeA stroke:#abc"), "flowchart") == []


def test_class_def_does_not_trigger() -> None:
    assert check_fill_no_color(_target("graph TD\nclassDef x fill:#abc"), "flowchart") == []


def test_line_inside_init_block_does_not_trigger() -> None:
    content = "graph TD\n%%{init:\nstyle NodeA fill:#abc\n}%%"
    assert check_fill_no_color(_target(content), "flowchart") == []

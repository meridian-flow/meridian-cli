"""Tests for Mermaid bare-end style check."""

from __future__ import annotations

from pathlib import Path

from meridian.lib.mermaid.scanner import DiagramTarget
from meridian.lib.mermaid.style.bare_end import check_bare_end


def _target(content: str) -> DiagramTarget:
    return DiagramTarget(Path("/tmp/design.md"), "design.md", content, 1, "standalone")


def test_edge_to_bare_end_triggers_warning() -> None:
    warnings = check_bare_end(_target("graph TD\nA --> end"), "flowchart")
    assert len(warnings) == 1


def test_edge_from_bare_end_triggers_warning() -> None:
    warnings = check_bare_end(_target("graph TD\nend --> B"), "flowchart")
    assert len(warnings) == 1


def test_standalone_end_line_does_not_trigger() -> None:
    content = "graph TD\nsubgraph X\nA --> B\nend"
    assert check_bare_end(_target(content), "flowchart") == []


def test_capitalized_end_does_not_trigger() -> None:
    assert check_bare_end(_target("graph TD\nA --> End"), "flowchart") == []


def test_quoted_end_label_does_not_trigger() -> None:
    assert check_bare_end(_target('graph TD\nA --> ["end"]'), "flowchart") == []


def test_non_flowchart_has_no_warnings() -> None:
    assert check_bare_end(_target("sequenceDiagram\nA --> end"), "sequence") == []

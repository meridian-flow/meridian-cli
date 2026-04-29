"""Tests for Mermaid ox-edge style check."""

from __future__ import annotations

from pathlib import Path

from meridian.lib.mermaid.scanner import DiagramTarget
from meridian.lib.mermaid.style.ox_edge import check_ox_edge


def _target(content: str) -> DiagramTarget:
    return DiagramTarget(Path("/tmp/design.md"), "design.md", content, 1, "standalone")


def test_triple_dash_o_lowercase_triggers_warning() -> None:
    warnings = check_ox_edge(_target("graph TD\nA ---obackend"), "flowchart")
    assert len(warnings) == 1


def test_triple_dash_x_lowercase_triggers_warning() -> None:
    warnings = check_ox_edge(_target("graph TD\nA ---xservice"), "flowchart")
    assert len(warnings) == 1


def test_space_after_o_does_not_trigger() -> None:
    assert check_ox_edge(_target("graph TD\nA ---o Backend"), "flowchart") == []


def test_uppercase_after_o_does_not_trigger() -> None:
    assert check_ox_edge(_target("graph TD\nA ---OBackend"), "flowchart") == []


def test_arrow_form_does_not_trigger() -> None:
    assert check_ox_edge(_target("graph TD\nA -->obackend"), "flowchart") == []


def test_dotted_arrow_form_does_not_trigger() -> None:
    assert check_ox_edge(_target("graph TD\nA -.->obackend"), "flowchart") == []


def test_non_flowchart_has_no_warnings() -> None:
    assert check_ox_edge(_target("sequenceDiagram\nA ---obackend"), "sequence") == []


def test_multiple_edges_on_same_line() -> None:
    warnings = check_ox_edge(_target("graph TD\nA ---obackend; B ---xservice"), "flowchart")
    assert len(warnings) == 2

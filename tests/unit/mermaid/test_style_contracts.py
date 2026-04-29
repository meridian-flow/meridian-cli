"""Contract tests for Mermaid style warning foundations."""

from __future__ import annotations

from pathlib import Path

from meridian.lib.mermaid.scanner import DiagramTarget
from meridian.lib.mermaid.style import get_all_categories, run_style_checks
from meridian.lib.mermaid.style.line_map import content_line_to_file_line
from meridian.lib.mermaid.style.types import StyleCheckOptions
from meridian.lib.mermaid.validator import BlockResult


def _target(*, start_line: int, source: str = "fenced-block") -> DiagramTarget:
    return DiagramTarget(
        file=Path("/tmp/design.md"),
        rel="design.md",
        content="graph TD\n    A --> B\n",
        start_line=start_line,
        source=source,
    )


def test_line_mapping_fenced_block_offsets_from_fence_line() -> None:
    assert content_line_to_file_line(_target(start_line=10), 3) == 13
    assert content_line_to_file_line(_target(start_line=1), 1) == 2
    assert content_line_to_file_line(_target(start_line=50), 7) == 57


def test_line_mapping_standalone_uses_content_line() -> None:
    assert content_line_to_file_line(_target(start_line=1, source="standalone"), 5) == 5
    assert content_line_to_file_line(_target(start_line=1, source="standalone"), 1) == 1


def test_run_style_checks_empty_targets_returns_empty_partitions() -> None:
    assert run_style_checks([], [], StyleCheckOptions()) == ([], [])


def test_run_style_checks_disabled_returns_empty_partitions() -> None:
    target = _target(start_line=10)
    validation = BlockResult(
        file="design.md",
        line=10,
        valid=True,
        diagram_type="flowchart",
    )

    assert run_style_checks([target], [validation], StyleCheckOptions(enabled=False)) == ([], [])


def test_run_style_checks_no_registered_checks_returns_empty_partitions() -> None:
    target = _target(start_line=10)
    validation = BlockResult(
        file="design.md",
        line=10,
        valid=True,
        diagram_type="flowchart",
    )

    assert run_style_checks([target], [validation], StyleCheckOptions()) == ([], [])


def test_public_import_paths_work() -> None:
    from meridian.lib.mermaid import CheckResult, StyleCheckOptions, StyleWarning
    from meridian.lib.mermaid.style import run_style_checks
    from meridian.lib.mermaid.style.line_map import content_line_to_file_line

    assert StyleWarning is not None
    assert StyleCheckOptions is not None
    assert CheckResult is not None
    assert run_style_checks is not None
    assert content_line_to_file_line is not None


def test_get_all_categories_returns_registered_categories_for_warning_phase() -> None:
    categories = get_all_categories()

    assert isinstance(categories, list)
    assert {category.id for category in categories} == {"bare-end", "ox-edge", "fill-no-color"}

"""Tests for Mermaid style registry orchestration."""

from __future__ import annotations

from pathlib import Path

from meridian.lib.mermaid.scanner import DiagramTarget
from meridian.lib.mermaid.style import get_all_categories, run_style_checks
from meridian.lib.mermaid.style.types import StyleCheckOptions
from meridian.lib.mermaid.validator import BlockResult


def _target(content: str = "graph TD\nA ---obackend\nstyle A fill:#abc") -> DiagramTarget:
    return DiagramTarget(Path("/tmp/design.md"), "design.md", content, 1, "standalone")


def _validation(*, valid: bool = True, diagram_type: str | None = "flowchart") -> BlockResult:
    return BlockResult("design.md", 1, valid, diagram_type=diagram_type)


def test_all_default_categories_are_registered() -> None:
    ids = {category.id for category in get_all_categories()}
    assert ids == {"bare-end", "ox-edge", "fill-no-color"}


def test_get_all_categories_returns_three_items() -> None:
    assert len(get_all_categories()) == 3


def test_disabled_categories_are_skipped() -> None:
    active, suppressed = run_style_checks(
        [_target()],
        [_validation()],
        StyleCheckOptions(disabled_categories={"ox-edge", "fill-no-color"}),
    )

    assert active == []
    assert suppressed == []


def test_pre_parse_warning_on_invalid_block_is_deduplicated() -> None:
    active, suppressed = run_style_checks(
        [_target("graph TD\nA ---obackend")], [_validation(valid=False)], StyleCheckOptions()
    )

    assert active == []
    assert suppressed == []


def test_post_parse_checks_skip_invalid_blocks() -> None:
    active, suppressed = run_style_checks(
        [_target("graph TD\nstyle A fill:#abc")], [_validation(valid=False)], StyleCheckOptions()
    )

    assert active == []
    assert suppressed == []


def test_suppression_partitions_warnings() -> None:
    target = _target("graph TD\n%% mermaid-check-ignore-next-line ox-edge\nA ---obackend")
    active, suppressed = run_style_checks([target], [_validation()], StyleCheckOptions())

    assert active == []
    assert len(suppressed) == 1
    assert suppressed[0].suppressed is True
    assert suppressed[0].suppression_source is not None

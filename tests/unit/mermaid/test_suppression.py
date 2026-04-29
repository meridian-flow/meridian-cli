"""Tests for Mermaid style suppression parsing."""

from __future__ import annotations

from meridian.lib.mermaid.style.suppression import parse_suppressions


def test_next_line_category_suppresses_only_next_line() -> None:
    suppressions = parse_suppressions(
        "%% mermaid-check-ignore-next-line ox-edge\nA ---obackend\nB ---xservice"
    )

    assert suppressions.is_suppressed(2, "ox-edge")[0] is True
    assert suppressions.is_suppressed(3, "ox-edge") == (False, None)
    assert suppressions.is_suppressed(2, "bare-end") == (False, None)


def test_block_category_suppresses_entire_block() -> None:
    suppressions = parse_suppressions(
        "%% mermaid-check-ignore ox-edge\nA ---obackend\nB ---xservice"
    )

    assert suppressions.is_suppressed(2, "ox-edge")[0] is True
    assert suppressions.is_suppressed(3, "ox-edge")[0] is True
    assert suppressions.is_suppressed(2, "bare-end") == (False, None)


def test_next_line_without_category_suppresses_all_categories() -> None:
    suppressions = parse_suppressions("%% mermaid-check-ignore-next-line\nA ---obackend")

    assert suppressions.is_suppressed(2, "ox-edge")[0] is True
    assert suppressions.is_suppressed(2, "bare-end")[0] is True


def test_block_without_category_suppresses_all_categories() -> None:
    suppressions = parse_suppressions("%% mermaid-check-ignore\nA ---obackend")

    assert suppressions.is_suppressed(2, "ox-edge")[0] is True
    assert suppressions.is_suppressed(2, "bare-end")[0] is True


def test_multiple_suppression_comments_apply() -> None:
    suppressions = parse_suppressions(
        "%% mermaid-check-ignore ox-edge\n%% mermaid-check-ignore-next-line bare-end\nA --> end"
    )

    assert suppressions.is_suppressed(3, "ox-edge")[0] is True
    assert suppressions.is_suppressed(3, "bare-end")[0] is True


def test_next_line_suppression_not_immediately_before_has_no_effect() -> None:
    suppressions = parse_suppressions(
        "%% mermaid-check-ignore-next-line ox-edge\nA --> B\nA ---obackend"
    )

    assert suppressions.is_suppressed(3, "ox-edge") == (False, None)


def test_misspelled_prefix_has_no_effect() -> None:
    suppressions = parse_suppressions("%% mermaid-ignore ox-edge\nA ---obackend")

    assert suppressions.is_suppressed(2, "ox-edge") == (False, None)


def test_suppression_at_last_line_is_harmless() -> None:
    suppressions = parse_suppressions("A --> B\n%% mermaid-check-ignore-next-line ox-edge")

    assert suppressions.is_suppressed(3, "ox-edge")[0] is True

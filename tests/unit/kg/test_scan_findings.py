"""Unit tests for kg content finding scans."""

from pathlib import Path

from meridian.lib.kg.graph import _scan_file_findings


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "notes.md"
    path.write_text(content, encoding="utf-8")
    return path


def _findings(tmp_path: Path, content: str) -> list[tuple[str, int]]:
    path = _write(tmp_path, content)
    return [(finding.category, finding.line) for finding in _scan_file_findings(path, "warning")]


def test_real_flag_and_conflict_outside_fences_detected(tmp_path):
    content = "\n".join(
        [
            "# Notes",
            "> [!FLAG]",
            "<<<<<<< HEAD",
            "left",
            "=======",
            "right",
            ">>>>>>> branch",
            "",
        ]
    )

    assert _findings(tmp_path, content) == [
        ("flag_block", 2),
        ("conflict_marker", 3),
        ("conflict_marker", 5),
        ("conflict_marker", 7),
    ]


def test_flag_and_conflict_inside_triple_backtick_fence_ignored(tmp_path):
    content = "\n".join(
        [
            "# Example",
            "```",
            "> [!FLAG]",
            "<<<<<<< HEAD",
            "=======",
            ">>>>>>> branch",
            "```",
            "",
        ]
    )

    assert _findings(tmp_path, content) == []


def test_four_backtick_fence_ignores_inner_triple_backticks(tmp_path):
    content = "\n".join(
        [
            "# Example",
            "````python",
            "```",
            "> [!FLAG]",
            "<<<<<<< HEAD",
            "=======",
            ">>>>>>> branch",
            "```",
            "````",
            "",
        ]
    )

    assert _findings(tmp_path, content) == []


def test_closing_fence_must_match_opening_char_and_length(tmp_path):
    content = "\n".join(
        [
            "# Example",
            "````",
            "> [!FLAG]",
            "```",
            "<<<<<<< HEAD",
            "~~~~",
            "=======",
            "````",
            "> [!FLAG]",
            "",
        ]
    )

    assert _findings(tmp_path, content) == [("flag_block", 9)]


def test_tilde_fences_suppress_findings(tmp_path):
    content = "\n".join(
        [
            "# Example",
            "~~~text",
            "> [!FLAG]",
            "<<<<<<< HEAD",
            "=======",
            ">>>>>>> branch",
            "~~~   ",
            "",
        ]
    )

    assert _findings(tmp_path, content) == []


def test_only_unfenced_findings_reported_when_fences_present(tmp_path):
    content = "\n".join(
        [
            "# Mixed",
            "```",
            "> [!FLAG]",
            "<<<<<<< HEAD",
            "=======",
            ">>>>>>> branch",
            "```",
            "> [!FLAG]",
            "<<<<<<< HEAD",
            "left",
            "=======",
            "right",
            ">>>>>>> branch",
            "~~~",
            "> [!FLAG]",
            "<<<<<<< HEAD",
            "~~~",
            "",
        ]
    )

    assert _findings(tmp_path, content) == [
        ("flag_block", 8),
        ("conflict_marker", 9),
        ("conflict_marker", 11),
        ("conflict_marker", 13),
    ]

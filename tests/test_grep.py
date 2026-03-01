"""Coverage for the grep operation and output formatting."""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian.lib.ops.grep import GrepInput, grep_sync


def _write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def grep_repo(tmp_path: Path) -> Path:
    _write_lines(
        tmp_path / ".meridian" / ".spaces" / "s91" / "runs" / "r10" / "output.jsonl",
        [
            "boot",
            "config set defaults.agent custom-agent-123",
            "noop",
            "config reset defaults.agent",
        ],
    )
    _write_lines(
        tmp_path / ".meridian" / ".spaces" / "s91" / "runs" / "r10" / "stderr.log",
        [
            "warning: recoverable",
        ],
    )
    _write_lines(
        tmp_path / ".meridian" / ".spaces" / "s91" / "runs" / "r11" / "output.jsonl",
        [
            "other run output",
        ],
    )
    _write_lines(
        tmp_path / ".meridian" / ".spaces" / "s91" / "runs.jsonl",
        [
            '{"event":"run.start","prompt":"find-me-in-runs"}',
        ],
    )
    _write_lines(
        tmp_path / ".meridian" / ".spaces" / "s91" / "sessions.jsonl",
        [
            '{"event":"session.start","chat_id":"c1"}',
        ],
    )
    _write_lines(
        tmp_path / ".meridian" / ".spaces" / "s127" / "runs" / "r2" / "stderr.log",
        [
            "line 1",
            "line 2",
            "line 3",
            "line 4",
            "line 5",
            "line 6",
            "line 7",
            "config set defaults.agent custom-agent-123",
        ],
    )
    _write_lines(
        tmp_path / ".meridian" / ".spaces" / "s127" / "runs.jsonl",
        [
            '{"event":"run.start","prompt":"no-match"}',
        ],
    )
    _write_lines(
        tmp_path / ".meridian" / ".spaces" / "s127" / "sessions.jsonl",
        [
            '{"event":"session.start","chat_id":"c2"}',
        ],
    )
    return tmp_path


def test_basic_pattern_search_finds_matches_across_spaces(grep_repo: Path) -> None:
    result = grep_sync(
        GrepInput(
            pattern=r"defaults\.agent",
            repo_root=grep_repo.as_posix(),
        )
    )
    assert result.total == 3
    assert [(m.space_id, m.run_id, m.file, m.line) for m in result.results] == [
        ("s127", "r2", "stderr.log", 8),
        ("s91", "r10", "output.jsonl", 2),
        ("s91", "r10", "output.jsonl", 4),
    ]


def test_space_filter_scopes_to_one_space(grep_repo: Path) -> None:
    result = grep_sync(
        GrepInput(
            pattern=r"defaults\.agent",
            space_id="s91",
            repo_root=grep_repo.as_posix(),
        )
    )
    assert result.total == 2
    assert {match.space_id for match in result.results} == {"s91"}


def test_space_and_run_filter_scopes_to_one_run(grep_repo: Path) -> None:
    result = grep_sync(
        GrepInput(
            pattern=r"defaults\.agent",
            space_id="s91",
            run_id="r10",
            repo_root=grep_repo.as_posix(),
        )
    )
    assert result.total == 2
    assert {match.run_id for match in result.results} == {"r10"}


def test_type_output_only_searches_output_jsonl(grep_repo: Path) -> None:
    result = grep_sync(
        GrepInput(
            pattern=r"defaults\.agent",
            file_type="output",
            repo_root=grep_repo.as_posix(),
        )
    )
    assert result.total == 2
    assert all(match.file == "output.jsonl" for match in result.results)


def test_type_logs_only_searches_stderr_log(grep_repo: Path) -> None:
    result = grep_sync(
        GrepInput(
            pattern=r"defaults\.agent",
            file_type="logs",
            repo_root=grep_repo.as_posix(),
        )
    )
    assert result.total == 1
    assert result.results[0].file == "stderr.log"
    assert result.results[0].space_id == "s127"


def test_no_matches_returns_empty_results(grep_repo: Path) -> None:
    result = grep_sync(
        GrepInput(
            pattern=r"will-not-match-anything",
            repo_root=grep_repo.as_posix(),
        )
    )
    assert result.total == 0
    assert result.results == ()


def test_invalid_regex_gives_clear_error(grep_repo: Path) -> None:
    with pytest.raises(ValueError, match="Invalid regex pattern"):
        grep_sync(
            GrepInput(
                pattern="(",
                repo_root=grep_repo.as_posix(),
            )
        )


def test_text_format_is_line_oriented_and_parseable(grep_repo: Path) -> None:
    result = grep_sync(
        GrepInput(
            pattern=r"defaults\.agent",
            repo_root=grep_repo.as_posix(),
        )
    )
    assert result.format_text().splitlines() == [
        "s127/r2/stderr.log:8: config set defaults.agent custom-agent-123",
        "s91/r10/output.jsonl:2: config set defaults.agent custom-agent-123",
        "s91/r10/output.jsonl:4: config reset defaults.agent",
    ]

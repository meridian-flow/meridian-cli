import logging
from pathlib import Path

import pytest

from meridian.lib.catalog.agent import parse_agent_profile


def _write_profile(tmp_path: Path, filename: str, frontmatter_lines: list[str]) -> Path:
    profile_path = tmp_path / filename
    profile_path.write_text(
        "\n".join(["---", *frontmatter_lines, "---", "", "Profile body.", ""]) + "\n",
        encoding="utf-8",
    )
    return profile_path


def test_parse_agent_profile_disallowed_tools(tmp_path: Path) -> None:
    profile_path = _write_profile(
        tmp_path,
        "coder.md",
        [
            "name: Coder",
            "tools:",
            "  - Read",
            "disallowed-tools:",
            "  - Bash",
            "  - WebSearch",
            "mcp-tools:",
            "  - mcpA",
        ],
    )

    profile = parse_agent_profile(profile_path)

    assert profile.tools == ("Read",)
    assert profile.disallowed_tools == ("Bash", "WebSearch")


def test_parse_agent_profile_models_preserves_supported_overrides(
    tmp_path: Path,
) -> None:
    profile_path = _write_profile(
        tmp_path,
        "reviewer.md",
        [
            "name: Reviewer",
            "models:",
            "  gpt55:",
            "    effort: low",
            "    autocompact: 35",
            "    lane: correctness",
            "  unknown-only:",
            "    custom_field: ok",
        ],
    )

    profile = parse_agent_profile(profile_path)

    assert tuple(profile.models.keys()) == ("gpt55", "unknown-only")
    assert profile.models["gpt55"].effort == "low"
    assert profile.models["gpt55"].autocompact == 35
    assert profile.models["unknown-only"].effort is None
    assert profile.models["unknown-only"].autocompact is None


def test_parse_agent_profile_fanout_is_display_only_alias_list(
    tmp_path: Path,
) -> None:
    profile_path = _write_profile(
        tmp_path,
        "reviewer.md",
        [
            "name: Reviewer",
            "models:",
            "  policy-only:",
            "    effort: low",
            "fanout:",
            "  - gpt54",
            "  - gpt55",
        ],
    )

    profile = parse_agent_profile(profile_path)

    assert tuple(profile.models.keys()) == ("policy-only",)
    assert profile.fanout == ("gpt54", "gpt55")


def test_parse_agent_profile_models_discards_invalid_entries_and_warns(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    profile_path = _write_profile(
        tmp_path,
        "planner.md",
        [
            "name: Planner",
            "models:",
            "  valid:",
            "    effort: medium",
            "  bad-effort:",
            "    effort: auto",
            "  bad-autocompact:",
            "    autocompact: 101",
            "  bad-autocompact-bool:",
            "    autocompact: true",
            "  '   ':",
            "    effort: low",
        ],
    )
    caplog.set_level(logging.WARNING, logger="meridian.lib.catalog.agent")

    profile = parse_agent_profile(profile_path)

    assert tuple(profile.models.keys()) == ("valid",)
    warning_text = "\n".join(record.message for record in caplog.records)
    assert "invalid models entry for 'bad-effort'" in warning_text
    assert "invalid models entry for 'bad-autocompact'" in warning_text
    assert "invalid models entry for 'bad-autocompact-bool'" in warning_text
    assert "empty models key" in warning_text


def test_parse_agent_profile_keeps_valid_profile_autocompact(tmp_path: Path) -> None:
    profile_path = _write_profile(
        tmp_path,
        "coder.md",
        [
            "name: Coder",
            "model: gpt-5.4",
            "autocompact: 40",
        ],
    )

    profile = parse_agent_profile(profile_path)
    assert profile.autocompact == 40


def test_parse_agent_profile_drops_out_of_range_profile_autocompact(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    profile_path = _write_profile(
        tmp_path,
        "coder.md",
        [
            "name: Coder",
            "model: gpt-5.4",
            "autocompact: 150",
        ],
    )
    caplog.set_level(logging.WARNING, logger="meridian.lib.catalog.agent")

    profile = parse_agent_profile(profile_path)
    assert profile.autocompact is None
    assert "outside valid range" in caplog.text

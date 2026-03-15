from pathlib import Path

from meridian.lib.catalog.agent import parse_agent_profile


def test_parse_agent_profile_reads_thinking_frontmatter(tmp_path: Path) -> None:
    profile_path = tmp_path / "coder.md"
    profile_path.write_text(
        "\n".join(
            [
                "---",
                "name: coder",
                "description: test coder",
                "model: gpt-5.3-codex",
                "thinking: xhigh",
                "---",
                "",
                "# Coder",
                "",
            ]
        ),
        encoding="utf-8",
    )

    profile = parse_agent_profile(profile_path)

    assert profile.thinking == "xhigh"

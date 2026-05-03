from pathlib import Path

import pytest

from meridian.lib.catalog.model_aliases import entry
from meridian.lib.launch.prompt import build_agent_inventory_prompt


def _write_profile(project_root: Path, filename: str, frontmatter_lines: list[str]) -> Path:
    profile_path = project_root / ".mars" / "agents" / filename
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        "\n".join(["---", *frontmatter_lines, "---", "", "Profile body.", ""]) + "\n",
        encoding="utf-8",
    )
    return profile_path


def test_build_agent_inventory_prompt_uses_real_profile_discovery_and_fanout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()

    _write_profile(
        project_root,
        "reviewer.md",
        [
            "name: Reviewer",
            "description: Explicit fanout",
            "models:",
            "  policy-only:",
            "    effort: low",
            "fanout:",
            "  - alias: gpt54",
            "  - alias: gpt55",
        ],
    )
    _write_profile(
        project_root,
        "orchestrator.md",
        [
            "name: Orchestrator",
            "description: Primary",
            "mode: primary",
        ],
    )

    monkeypatch.setattr(
        "meridian.lib.launch.prompt.load_merged_aliases",
        lambda *, project_root: [
            entry(alias="gpt54", model_id="gpt-5.4"),
            entry(alias="gpt55", model_id="gpt-5.5"),
            entry(alias="policy-only", model_id="gpt-policy"),
        ],
    )

    prompt = build_agent_inventory_prompt(project_root=project_root)

    assert prompt is not None
    assert prompt.splitlines()[4:] == [
        "## Primary",
        "- Orchestrator: Primary",
        "",
        "## Subagent",
        "- Reviewer: Explicit fanout | Fan-out: gpt54, gpt55",
    ]
    assert "policy-only" not in prompt

from __future__ import annotations

from pathlib import Path

from meridian.lib.catalog.agent import AgentModelEntry, AgentProfile
from meridian.lib.catalog.model_aliases import entry
from meridian.lib.launch.prompt import (
    _dedupe_fan_out_aliases,
    _get_fan_out_aliases,
    build_agent_inventory_prompt,
)


def _profile(
    *,
    tmp_path: Path,
    name: str,
    description: str,
    model: str | None = None,
    models: dict[str, AgentModelEntry] | None = None,
    fanout: tuple[str, ...] = (),
) -> AgentProfile:
    return AgentProfile(
        name=name,
        description=description,
        model=model,
        harness=None,
        skills=(),
        tools=(),
        disallowed_tools=(),
        mcp_tools=(),
        sandbox=None,
        effort=None,
        approval=None,
        autocompact=None,
        models=models or {},
        fanout=fanout,
        body="",
        path=tmp_path / f"{name}.md",
        raw_content="",
    )


def test_build_agent_inventory_prompt_returns_none_without_agents(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "meridian.lib.launch.prompt.scan_agent_profiles",
        lambda project_root: [],
    )

    assert build_agent_inventory_prompt(project_root=tmp_path) is None


def test_build_agent_inventory_prompt_renders_model_and_fan_out_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    profiles = [
        _profile(
            tmp_path=tmp_path,
            name="zeta",
            description="No model metadata",
        ),
        _profile(
            tmp_path=tmp_path,
            name="beta",
            description="Fan-out only",
            models={"opus46": AgentModelEntry()},
        ),
        _profile(
            tmp_path=tmp_path,
            name="alpha",
            description="Primary reviewer",
            model="gpt54",
            models={
                "gpt54": AgentModelEntry(),
                "gpt55": AgentModelEntry(),
                "dup55": AgentModelEntry(),
                "unknown_alias": AgentModelEntry(),
            },
        ),
    ]
    alias_load_count = 0

    def fake_scan(*, project_root: Path) -> list[AgentProfile]:
        assert project_root == tmp_path
        return profiles

    def fake_load(*, project_root: Path):
        nonlocal alias_load_count
        assert project_root == tmp_path
        alias_load_count += 1
        return [
            entry(alias="gpt54", model_id="gpt-5.4"),
            entry(alias="gpt55", model_id="gpt-5.5"),
            entry(alias="dup55", model_id="gpt-5.5"),
            entry(alias="opus46", model_id="claude-opus-4-6"),
        ]

    monkeypatch.setattr("meridian.lib.launch.prompt.scan_agent_profiles", fake_scan)
    monkeypatch.setattr("meridian.lib.launch.prompt.load_merged_aliases", fake_load)

    prompt = build_agent_inventory_prompt(project_root=tmp_path)

    assert prompt is not None
    assert alias_load_count == 1
    lines = prompt.splitlines()
    assert lines[0] == "# Meridian Agents"
    assert lines[4] == "AGENTS"
    assert (
        "- alpha: Primary reviewer | Model: gpt54 | Fan-out: gpt54, gpt55, unknown_alias"
        in lines
    )
    assert "- beta: Fan-out only | Fan-out: opus46" in lines
    assert "- zeta: No model metadata" in lines


def test_build_agent_inventory_prompt_uses_explicit_fanout_for_display(
    monkeypatch,
    tmp_path: Path,
) -> None:
    profiles = [
        _profile(
            tmp_path=tmp_path,
            name="reviewer",
            description="Explicit fanout",
            models={"policy-only": AgentModelEntry()},
            fanout=("gpt54", "gpt55"),
        ),
    ]

    monkeypatch.setattr(
        "meridian.lib.launch.prompt.scan_agent_profiles",
        lambda *, project_root: profiles,
    )
    monkeypatch.setattr(
        "meridian.lib.launch.prompt.load_merged_aliases",
        lambda *, project_root: [
            entry(alias="gpt54", model_id="gpt-5.4"),
            entry(alias="gpt55", model_id="gpt-5.5"),
            entry(alias="policy-only", model_id="gpt-policy"),
        ],
    )

    prompt = build_agent_inventory_prompt(project_root=tmp_path)

    assert prompt is not None
    assert "- reviewer: Explicit fanout | Fan-out: gpt54, gpt55" in prompt.splitlines()
    assert "policy-only" not in prompt


def test_get_fan_out_aliases_falls_back_to_models_keys(tmp_path: Path) -> None:
    profile = _profile(
        tmp_path=tmp_path,
        name="reviewer",
        description="Fallback",
        models={"gpt54": AgentModelEntry(), "gpt55": AgentModelEntry()},
    )

    assert _get_fan_out_aliases(profile) == ("gpt54", "gpt55")


def test_get_fan_out_aliases_prefers_explicit_fanout(tmp_path: Path) -> None:
    profile = _profile(
        tmp_path=tmp_path,
        name="reviewer",
        description="Explicit",
        models={"policy-only": AgentModelEntry()},
        fanout=("gpt54", "gpt55"),
    )

    assert _get_fan_out_aliases(profile) == ("gpt54", "gpt55")


# --- _dedupe_fan_out_aliases ---


def test_dedupe_fan_out_aliases_keeps_first_alias_for_each_resolved_model() -> None:
    catalog = {
        "gpt54": entry(alias="gpt54", model_id="gpt-5.4"),
        "gpt": entry(alias="gpt", model_id="gpt-5.4"),
        "opus": entry(alias="opus", model_id="claude-opus-4-6"),
        "opus46": entry(alias="opus46", model_id="claude-opus-4-6"),
    }
    result = _dedupe_fan_out_aliases(["gpt54", "gpt", "opus", "opus46"], catalog)
    assert result == ["gpt54", "opus"]


def test_dedupe_fan_out_aliases_preserves_unknown_aliases_verbatim() -> None:
    catalog = {
        "gpt": entry(alias="gpt", model_id="gpt-5.5"),
        "gpt55": entry(alias="gpt55", model_id="gpt-5.5"),
    }
    result = _dedupe_fan_out_aliases(
        ["gpt", "custom-gpt", "gpt55", "another-custom"],
        catalog,
    )
    assert result == ["gpt", "custom-gpt", "another-custom"]

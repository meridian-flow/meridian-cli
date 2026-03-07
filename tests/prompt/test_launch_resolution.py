"""Launch-time profile, skill, and permission resolution invariants."""

from __future__ import annotations

from pathlib import Path

from meridian.lib.config.agent import AgentProfile
from meridian.lib.launch_resolve import (
    load_agent_profile_with_fallback,
    resolve_permission_tier_from_profile,
    resolve_skills_from_profile,
)
from tests.helpers.fixtures import write_agent as _write_agent
from tests.helpers.fixtures import write_skill as _write_skill


def test_permission_tier_from_sandbox() -> None:
    profile = AgentProfile(
        name="lead-primary",
        description="",
        model="claude-sonnet-4-6",
        variant=None,
        skills=(),
        allowed_tools=(),
        mcp_tools=(),
        sandbox="danger-full-access",
        variant_models=(),
        body="",
        path=Path("lead-primary.md"),
        raw_content="",
    )

    assert resolve_permission_tier_from_profile(
        profile=profile,
        default_tier="read-only",
    ) == "full-access"


def test_load_agent_profile_with_fallback_prefers_requested_agent(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_agent(repo_root, name="requested", model="gpt-5.3-codex", body="# requested")
    _write_agent(repo_root, name="agent", model="claude-sonnet-4-6", body="# fallback")

    loaded = load_agent_profile_with_fallback(
        repo_root=repo_root,
        requested_agent="requested",
        configured_default="agent",
    )

    assert loaded is not None
    assert loaded.name == "requested"
    assert loaded.body.strip() == "# requested"


def test_resolve_skills_from_profile_keeps_missing_skills_separate(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_skill(repo_root, "alpha", "alpha body")

    resolved = resolve_skills_from_profile(
        profile_skills=("alpha", "missing"),
        repo_root=repo_root,
    )

    assert resolved.skill_names == ("alpha",)
    assert tuple(skill.name for skill in resolved.loaded_skills) == ("alpha",)
    assert resolved.missing_skills == ("missing",)
    assert resolved.skill_sources["alpha"].name == "alpha"

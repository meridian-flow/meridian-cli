from pathlib import Path

from meridian.lib.catalog.agent import AgentProfile
from meridian.lib.config.settings import load_config
from meridian.lib.core.domain import SkillContent
from meridian.lib.core.types import HarnessId
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.install.bootstrap import BootstrapPlan
from meridian.lib.launch.plan import resolve_primary_launch_plan
from meridian.lib.launch.resolve import ResolvedPolicies, ResolvedSkills
from meridian.lib.launch.types import LaunchRequest


def test_resolve_primary_launch_plan_prefixes_agent_profile_for_codex(
    monkeypatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    harness_registry = get_default_harness_registry()
    config = load_config(repo_root)
    codex_adapter = harness_registry.get_subprocess_harness(HarnessId.CODEX)

    profile = AgentProfile(
        name="coder",
        description="Codex coder",
        model="gpt-5.3-codex",
        harness="codex",
        skills=("review",),
        tools=(),
        mcp_tools=(),
        sandbox=None,
        thinking=None,
        body="Follow the agent contract.",
        path=repo_root / ".agents" / "agents" / "coder.md",
        raw_content="---\nname: coder\n---\n",
    )
    skill = SkillContent(
        name="review",
        description="Review instructions",
        content="Be strict.",
        path=(repo_root / ".agents" / "skills" / "review" / "SKILL.md").as_posix(),
    )

    monkeypatch.setattr(
        "meridian.lib.launch.plan.ensure_bootstrap_ready",
        lambda **kwargs: BootstrapPlan(required_items=(), missing_items=()),
    )
    monkeypatch.setattr(
        "meridian.lib.launch.plan.resolve_policies",
        lambda **kwargs: ResolvedPolicies(
            profile=profile,
            model="gpt-5.3-codex",
            harness=HarnessId.CODEX,
            adapter=codex_adapter,
            resolved_skills=ResolvedSkills(
                skill_names=("review",),
                loaded_skills=(skill,),
                skill_sources={"review": repo_root / ".agents" / "skills" / "review"},
                missing_skills=(),
            ),
            warning=None,
        ),
    )

    plan = resolve_primary_launch_plan(
        repo_root=repo_root,
        request=LaunchRequest(model="gpt-5.3-codex", harness="codex", agent="coder", fresh=True),
        harness_registry=harness_registry,
        config=config,
    )

    prompt = plan.run_params.prompt
    assert prompt.startswith("# Agent Profile\n\nFollow the agent contract.")
    assert f"# Skill: {skill.path}" in prompt
    assert "# Agent Profile\n\nFollow the agent contract." in prompt
    assert prompt.index("# Agent Profile") < prompt.index(f"# Skill: {skill.path}")
    assert prompt.index(f"# Skill: {skill.path}") < prompt.index("# Meridian Session")

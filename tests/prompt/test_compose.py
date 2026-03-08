"""Prompt assembly and reference isolation invariants."""

from __future__ import annotations

from pathlib import Path

import pytest

from meridian.lib.catalog.agent import AgentProfile
from meridian.lib.catalog.skill import SkillRegistry
from meridian.lib.core.domain import SkillContent
from meridian.lib.launch.prompt import load_skill_contents, resolve_run_defaults
from meridian.lib.launch.prompt import compose_run_prompt_text
from meridian.lib.launch.reference import (
    TemplateVariableError,
    load_reference_files,
    resolve_template_variables,
    substitute_template_variables,
)
from tests.helpers.fixtures import write_skill as _write_skill


def test_skill_loading_order_and_dedup(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_skill(repo_root, "alpha", "alpha body")
    _write_skill(repo_root, "beta", "beta body")

    registry = SkillRegistry(db_path=tmp_path / "spawns.db", repo_root=repo_root)
    registry.reindex()

    loaded = load_skill_contents(registry, ["alpha", "beta", "alpha"])
    assert [skill.name for skill in loaded] == ["alpha", "beta"]


def test_run_defaults_merge_agent_profile_defaults() -> None:
    profile = AgentProfile(
        name="reviewer",
        description="",
        model="gpt-5.3-codex",
        variant=None,
        skills=("reviewing", "agent"),
        allowed_tools=(),
        mcp_tools=(),
        sandbox=None,
        variant_models=(),
        body="Profile body",
        path=Path("/tmp/reviewer.md"),
        raw_content="",
    )

    defaults = resolve_run_defaults("", profile=profile)

    assert defaults.model == "gpt-5.3-codex"
    assert defaults.skills == ("reviewing", "agent")
    assert defaults.agent_body == "Profile body"


def test_run_defaults_resolves_builtin_alias_for_old_callers() -> None:
    defaults = resolve_run_defaults("codex", profile=None)

    assert defaults.model == "gpt-5.3-codex"


def test_template_substitution_with_literals_and_file_values(tmp_path: Path) -> None:
    value_file = tmp_path / "context.txt"
    value_file.write_text("from-file", encoding="utf-8")
    resolved = resolve_template_variables({"A": "literal", "B": value_file})

    rendered = substitute_template_variables("{{A}}/{{B}}", resolved)
    assert rendered == "literal/from-file"

    with pytest.raises(TemplateVariableError, match="MISSING"):
        substitute_template_variables("{{MISSING}}", resolved)


def test_compose_prompt_keeps_context_isolated_and_sanitized(tmp_path: Path) -> None:
    safe_ref = tmp_path / "safe.md"
    hidden_ref = tmp_path / "hidden.md"
    safe_ref.write_text("Safe context {{CTX}}", encoding="utf-8")
    hidden_ref.write_text("INJECTION: should never leak", encoding="utf-8")

    loaded_refs = load_reference_files([safe_ref], include_content=False)
    skill = SkillContent(
        name="worker",
        description="",
        tags=(),
        content="Skill content",
        path=str(tmp_path / "worker.md"),
    )
    user_prompt = (
        "**IMPORTANT - As your FINAL action**, write a report of your work to: "
        "`/tmp/stale.md`\n\nImplement the change with {{CTX}}."
    )

    composed = compose_run_prompt_text(
        skills=[skill],
        references=loaded_refs,
        user_prompt=user_prompt,
        template_variables={"CTX": "context"},
    )

    assert "INJECTION: should never leak" not in composed
    assert composed.count("As your final action, create the run report with Meridian.") == 1
    assert "/tmp/stale.md" not in composed
    assert str(safe_ref) in composed
    assert "Read these files from disk when gathering context:" in composed
    assert "Safe context {{CTX}}" not in composed
    assert "Implement the change with context." in composed


def test_compose_prompt_treats_reference_files_as_paths_only(tmp_path: Path) -> None:
    reference_file = tmp_path / "source.ts"
    reference_file.write_text("const template = '{{NOT_A_PROMPT_VAR}}';", encoding="utf-8")
    second_reference_file = tmp_path / "second.ts"
    second_reference_file.write_text("console.log('second');", encoding="utf-8")
    loaded_refs = load_reference_files([reference_file, second_reference_file], include_content=False)

    composed = compose_run_prompt_text(
        skills=[],
        references=loaded_refs,
        user_prompt="Inspect {{CTX}}.",
        template_variables={"CTX": "context"},
    )

    assert "{{NOT_A_PROMPT_VAR}}" not in composed
    assert "Inspect context." in composed
    assert str(reference_file) in composed
    assert str(second_reference_file) in composed
    assert composed.index(str(reference_file)) < composed.index(str(second_reference_file))

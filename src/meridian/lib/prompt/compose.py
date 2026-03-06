"""Prompt composition pipeline."""

from __future__ import annotations

import importlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from meridian.lib.domain import SkillContent
from meridian.lib.prompt.reference import (
    ReferenceFile,
    render_reference_blocks,
    render_reference_paths_section,
    resolve_template_variables,
    substitute_template_variables,
)
from meridian.lib.prompt.sanitize import sanitize_prior_output, strip_stale_report_paths


def build_report_instruction() -> str:
    """Build the report instruction appended to each composed run prompt."""

    return (
        "# Report\n\n"
        "**IMPORTANT - As your final action, create the run report with Meridian.**\n\n"
        "Run `meridian report create --stdin` and provide a plain markdown report via stdin.\n\n"
        "Include: what was done, key decisions made, files created/modified, "
        "verification results, and any issues or blockers.\n\n"
        "If `meridian report create` is unavailable or fails, provide the same markdown "
        "as your final assistant message so fallback extraction can persist the report."
    )


def _render_skill_blocks(skills: Sequence[SkillContent]) -> tuple[str, ...]:
    blocks: list[str] = []
    for skill in skills:
        content = skill.content.strip()
        if not content:
            continue
        blocks.append(f"# Skill: {skill.name}\n\n{content}")
    return tuple(blocks)


def _join_sections(sections: Sequence[str]) -> str:
    non_empty = [section.strip() for section in sections if section.strip()]
    return "\n\n".join(non_empty)


def _render_templated_section(
    section_text: str,
    variables: Mapping[str, str],
) -> str:
    return substitute_template_variables(section_text, variables)


def compose_skill_injections(skills: Sequence[SkillContent]) -> str | None:
    """Format skill content for --append-system-prompt injection.

    Includes full skill filepath and content (not frontmatter).
    Returns None when there are no skills (caller omits the flag entirely).
    """
    blocks: list[str] = []
    for skill in skills:
        content = skill.content.strip()
        if not content:
            continue
        blocks.append(f"# Skill: {skill.path}\n\n{content}")

    if not blocks:
        return None
    return _join_sections(blocks)


def compose_run_prompt(
    *,
    skills: Sequence[SkillContent],
    references: Sequence[ReferenceFile],
    user_prompt: str,
    agent_body: str = "",
    template_variables: Mapping[str, str | Path] | None = None,
    prior_output: str | None = None,
    reference_mode: Literal["inline", "paths"] = "inline",
) -> str:
    """Compose a run prompt with deterministic ordering and sanitization.

    Prompt assembly order:
    1) Skill content
    2) Agent profile body
    3) Reference files
    4) Template variable substitution
    5) Report path instruction
    6) User prompt
    """

    skill_sections = _render_skill_blocks(skills)
    non_skill_sections: list[str] = []
    resolved_variables = resolve_template_variables(template_variables or {})

    agent_body_text = agent_body.strip()
    if agent_body_text:
        non_skill_sections.append(
            _render_templated_section(f"# Agent Profile\n\n{agent_body_text}", resolved_variables)
        )

    if reference_mode == "paths":
        non_skill_sections.extend(render_reference_paths_section(references))
    else:
        non_skill_sections.extend(render_reference_blocks(references))

    if prior_output is not None and prior_output.strip():
        non_skill_sections.append(sanitize_prior_output(prior_output))

    rendered_non_skill_text = _join_sections(non_skill_sections)
    sections_text = _join_sections((*skill_sections, rendered_non_skill_text))
    cleaned_user_prompt = substitute_template_variables(
        strip_stale_report_paths(user_prompt),
        resolved_variables,
    )
    report_instruction = build_report_instruction()

    if sections_text:
        return f"""{sections_text}

{report_instruction}

{cleaned_user_prompt}
"""
    return f"""{report_instruction}

{cleaned_user_prompt}
"""


def compose_run_prompt_text(
    *,
    skills: Sequence[SkillContent],
    references: Sequence[ReferenceFile],
    user_prompt: str,
    agent_body: str = "",
    template_variables: Mapping[str, str | Path] | None = None,
    prior_output: str | None = None,
    reference_mode: Literal["inline", "paths"] = "inline",
) -> str:
    """Compose and render prompt text."""

    return compose_run_prompt(
        skills=skills,
        references=references,
        user_prompt=user_prompt,
        agent_body=agent_body,
        template_variables=template_variables,
        prior_output=prior_output,
        reference_mode=reference_mode,
    ).strip()


def render_file_template(
    template_path: Path,
    variables: Mapping[str, object],
    *,
    engine: Literal["t-string", "jinja2"] = "t-string",
) -> str:
    """Render template file with stdlib substitution or optional Jinja2 fallback."""

    content = template_path.read_text(encoding="utf-8")
    if engine == "jinja2":
        try:
            jinja2_module = importlib.import_module("jinja2")
        except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "Jinja2 fallback requested but jinja2 is not installed. "
                "Install with `meridian-channel[templates]`."
            ) from exc

        environment_cls = jinja2_module.Environment
        strict_undefined = jinja2_module.StrictUndefined
        env = environment_cls(
            autoescape=False,
            keep_trailing_newline=True,
            undefined=strict_undefined,
        )
        template = env.from_string(content)
        return str(template.render(**dict(variables)))

    normalized = {key: str(value) for key, value in variables.items()}
    return substitute_template_variables(content, normalized)

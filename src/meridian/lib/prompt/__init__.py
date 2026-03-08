"""Prompt composition helpers."""

from meridian.lib.launch.prompt import (
    dedupe_skill_contents,
    dedupe_skill_names,
    load_skill_contents,
    resolve_run_defaults,
    build_report_instruction,
    compose_run_prompt,
    compose_run_prompt_text,
    compose_skill_injections,
    render_file_template,
)
from meridian.lib.launch.reference import (
    ReferenceFile,
    TemplateVariableError,
    load_reference_files,
    parse_template_assignments,
    render_reference_blocks,
    render_reference_paths_section,
    resolve_template_variables,
    substitute_template_variables,
)
from meridian.lib.launch.prompt import sanitize_prior_output, strip_stale_report_paths

__all__ = [
    "ReferenceFile",
    "TemplateVariableError",
    "build_report_instruction",
    "compose_run_prompt",
    "compose_run_prompt_text",
    "compose_skill_injections",
    "dedupe_skill_contents",
    "dedupe_skill_names",
    "load_reference_files",
    "load_skill_contents",
    "parse_template_assignments",
    "render_file_template",
    "render_reference_blocks",
    "render_reference_paths_section",
    "resolve_run_defaults",
    "resolve_template_variables",
    "sanitize_prior_output",
    "strip_stale_report_paths",
    "substitute_template_variables",
]

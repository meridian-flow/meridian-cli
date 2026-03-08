"""Compatibility shim for prompt reference helpers."""

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

__all__ = [
    "ReferenceFile",
    "TemplateVariableError",
    "load_reference_files",
    "parse_template_assignments",
    "render_reference_blocks",
    "render_reference_paths_section",
    "resolve_template_variables",
    "substitute_template_variables",
]

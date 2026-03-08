"""Compatibility shim for prompt assembly helpers."""

from meridian.lib.launch.prompt import (
    DEFAULT_MODEL,
    SpawnPromptDefaults,
    dedupe_skill_contents,
    dedupe_skill_names,
    load_skill_contents,
    resolve_run_defaults,
)

__all__ = [
    "DEFAULT_MODEL",
    "SpawnPromptDefaults",
    "dedupe_skill_contents",
    "dedupe_skill_names",
    "load_skill_contents",
    "resolve_run_defaults",
]

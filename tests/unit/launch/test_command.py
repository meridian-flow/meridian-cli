from __future__ import annotations

from pathlib import Path

from meridian.lib.core.types import ModelId
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.launch_spec import ClaudeLaunchSpec, OpenCodeLaunchSpec
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.launch.command import build_launch_argv, resolve_launch_spec_stage
from meridian.lib.launch.reference import ReferenceItem
from meridian.lib.launch.run_inputs import ResolvedRunInputs
from meridian.lib.safety.permissions import PermissionConfig, TieredPermissionResolver


def _resolver() -> TieredPermissionResolver:
    return TieredPermissionResolver(config=PermissionConfig())


def test_build_launch_argv_preserves_opencode_reference_items_for_file_injection() -> None:
    adapter = OpenCodeAdapter()
    file_ref = ReferenceItem(
        kind="file",
        path=Path("/repo/src/main.py"),
        body="print('ok')",
    )
    run_inputs = ResolvedRunInputs(
        prompt="do thing",
        model=ModelId("opencode-gpt-5.4"),
        reference_items=(file_ref,),
    )
    perms = _resolver()
    projected_spec = resolve_launch_spec_stage(
        adapter=adapter,
        run_inputs=run_inputs,
        perms=perms,
    )
    assert isinstance(projected_spec, OpenCodeLaunchSpec)

    argv = build_launch_argv(
        adapter=adapter,
        run_inputs=run_inputs,
        perms=perms,
        projected_spec=projected_spec,
    )

    assert "--file" in argv
    assert file_ref.path.as_posix() in argv
    assert argv[-2:] == ("--", "-")


def test_build_launch_argv_projects_claude_prompt_file_path_from_resolved_spec() -> None:
    adapter = ClaudeAdapter()
    prompt_file_path = "/tmp/.meridian/spawns/p123/prompt.md"
    projected_spec = ClaudeLaunchSpec(
        prompt="do thing",
        permission_resolver=_resolver(),
        appended_system_prompt="injected system prompt",
        prompt_file_path=prompt_file_path,
    )

    argv = build_launch_argv(
        adapter=adapter,
        run_inputs=ResolvedRunInputs(prompt="ignored by projection"),
        perms=_resolver(),
        projected_spec=projected_spec,
    )

    assert "--append-system-prompt-file" in argv
    flag_index = argv.index("--append-system-prompt-file")
    assert argv[flag_index + 1] == prompt_file_path
    assert "--append-system-prompt" not in argv

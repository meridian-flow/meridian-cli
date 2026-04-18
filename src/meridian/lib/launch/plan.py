"""Primary-launch input builders."""

import os
from pathlib import Path

from meridian.lib.config.settings import MeridianConfig, load_config, resolve_project_root
from meridian.lib.state.paths import resolve_runtime_state_root

from .request import (
    LaunchArgvIntent,
    LaunchCompositionSurface,
    LaunchRuntime,
    SessionRequest,
    SpawnRequest,
)
from .types import LaunchRequest, SessionMode, build_primary_prompt

_DRY_RUN_REPORT_PATH = "<spawn-report-path>"


def _normalize_primary_session(request: LaunchRequest) -> SessionRequest:
    return request.session.model_copy(
        update={
            "requested_harness_session_id": (
                (request.session.requested_harness_session_id or "").strip() or None
            ),
            "continue_harness": (request.session.continue_harness or "").strip() or None,
            "continue_chat_id": (request.session.continue_chat_id or "").strip() or None,
            "continue_fork": (
                request.session.continue_fork
                or request.session_mode == SessionMode.FORK
            ),
            "primary_session_mode": request.session_mode.value,
        }
    )


def build_primary_spawn_request(
    *,
    request: LaunchRequest,
    prompt: str | None = None,
) -> SpawnRequest:
    """Translate primary launch inputs into the factory request shape."""

    normalized_session = _normalize_primary_session(request)
    base_prompt = prompt if prompt is not None else build_primary_prompt(request)

    return SpawnRequest(
        prompt=base_prompt,
        prompt_is_composed=False,
        model=(request.model or "").strip() or None,
        harness=(request.harness or "").strip() or None,
        agent=(request.agent or "").strip() or None,
        extra_args=request.passthrough_args,
        sandbox=request.sandbox,
        approval=request.approval,
        autocompact=request.autocompact,
        effort=request.effort,
        session=normalized_session,
        work_id_hint=(request.work_id or "").strip() or None,
    )


def build_primary_launch_runtime(
    *,
    repo_root: Path,
    config: MeridianConfig | None = None,
) -> LaunchRuntime:
    """Build primary-launch runtime inputs for the shared launch factory."""

    resolved_root = resolve_project_root(repo_root)
    resolved_config = config if config is not None else load_config(resolved_root)
    state_root = resolve_runtime_state_root(resolved_root)

    return LaunchRuntime(
        argv_intent=LaunchArgvIntent.REQUIRED,
        composition_surface=LaunchCompositionSurface.PRIMARY,
        config_snapshot=resolved_config.model_dump(mode="json", exclude_none=True),
        harness_command_override=os.getenv("MERIDIAN_HARNESS_COMMAND", "").strip() or None,
        report_output_path=_DRY_RUN_REPORT_PATH,
        state_root=state_root.as_posix(),
        project_paths_repo_root=resolved_root.as_posix(),
        project_paths_execution_cwd=resolved_root.as_posix(),
    )


__all__ = [
    "build_primary_launch_runtime",
    "build_primary_spawn_request",
]

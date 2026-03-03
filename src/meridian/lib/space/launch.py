"""Primary agent launcher helpers."""

from __future__ import annotations

import json
import logging
import os
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from meridian.lib.config._paths import resolve_repo_root
from meridian.lib.config.routing import route_model
from meridian.lib.config.settings import MeridianConfig, load_config
from meridian.lib.domain import SpaceState
from meridian.lib.exec.spawn import HARNESS_ENV_PASS_THROUGH, sanitize_child_env
from meridian.lib.harness.materialize import cleanup_materialized, materialize_for_harness
from meridian.lib.launch_resolve import (
    load_agent_profile_with_fallback,
    resolve_permission_tier_from_profile,
    resolve_skills_from_profile,
)
from meridian.lib.prompt.assembly import resolve_run_defaults
from meridian.lib.prompt.compose import compose_skill_injections
from meridian.lib.safety.permissions import (
    warn_profile_tier_escalation,
    build_permission_config,
    build_permission_resolver,
)
from meridian.lib.space.session_store import start_session, stop_session
from meridian.lib.space import space_file
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_space_dir, resolve_state_paths
from meridian.lib.types import HarnessId, ModelId, SpaceId

_CONTINUATION_GUIDANCE = (
    "You are resuming an existing space. Continue from the current state, "
    "preserve prior decisions unless evidence has changed, and avoid duplicating "
    "already-completed work."
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SpaceLaunchRequest:
    """Inputs for launching one primary agent session."""

    space_id: SpaceId
    model: str = ""
    agent: str | None = None
    fresh: bool = False
    autocompact: int | None = None
    passthrough_args: tuple[str, ...] = ()
    pinned_context: str = ""
    dry_run: bool = False
    permission_tier: str | None = None
    unsafe: bool = False


@dataclass(frozen=True, slots=True)
class SpaceLaunchResult:
    """Result metadata from a completed primary launch."""

    command: tuple[str, ...]
    exit_code: int
    final_state: SpaceState
    lock_path: Path


@dataclass(frozen=True, slots=True)
class _PrimarySessionMetadata:
    harness: str
    model: str
    agent: str
    agent_path: str
    skills: tuple[str, ...]
    skill_paths: tuple[str, ...]


def space_lock_path(repo_root: Path, space_id: SpaceId) -> Path:
    """Return active space lock path for one space ID."""

    return resolve_state_paths(repo_root).active_spaces_dir / f"{space_id}.lock"


def build_primary_prompt(request: SpaceLaunchRequest) -> str:
    """Build launch prompt for space start/resume sessions."""

    sections: list[str] = [
        "# Meridian Space Session",
        f"Space: {request.space_id}",
    ]

    if request.fresh:
        sections.extend(
            [
                "",
                "# Session Mode",
                "",
                "Start a fresh primary conversation for this space.",
            ]
        )
    else:
        sections.extend(["", "# Continuation Guidance", "", _CONTINUATION_GUIDANCE])

    if request.pinned_context.strip():
        sections.extend(["", "# Re-Injected Pinned Context", "", request.pinned_context.strip()])

    return "\n".join(sections).strip()


def _write_lock(
    *,
    path: Path,
    space_id: SpaceId,
    command: tuple[str, ...],
    child_pid: int | None,
) -> None:
    payload = {
        "space_id": str(space_id),
        "parent_pid": os.getpid(),
        "child_pid": child_pid,
        "started_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": list(command),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _build_interactive_command(
    *,
    repo_root: Path | None = None,
    request: SpaceLaunchRequest,
    prompt: str,
    passthrough_args: tuple[str, ...],
    chat_id: str = "",
    config: MeridianConfig | None = None,
) -> tuple[str, ...]:
    """Build interactive CLI command for space sessions."""

    override = os.getenv("MERIDIAN_HARNESS_COMMAND", "").strip()
    if override:
        command = [*shlex.split(override), *passthrough_args]
        if not command:
            raise ValueError("MERIDIAN_HARNESS_COMMAND resolved to an empty command.")
        return tuple(command)

    resolved_root = resolve_repo_root(repo_root)
    resolved_config = config if config is not None else load_config(resolved_root)
    profile = load_agent_profile_with_fallback(
        repo_root=resolved_root,
        search_paths=resolved_config.search_paths,
        requested_agent=request.agent,
        configured_default=resolved_config.default_primary_agent,
        fallback_name="primary",
    )

    defaults = resolve_run_defaults(
        request.model,
        profile=profile,
    )
    model = ModelId(defaults.model)
    harness = _resolve_harness(model=model)
    resolved_skills = resolve_skills_from_profile(
        profile_skills=defaults.skills,
        repo_root=resolved_root,
        search_paths=resolved_config.search_paths,
        readonly=True,
    )
    if resolved_skills.missing_skills:
        logger.warning(
            "Skipped unavailable skills for primary agent: %s",
            ", ".join(resolved_skills.missing_skills),
        )
    resolved_skill_sources = resolved_skills.skill_sources

    materialization_chat_id = chat_id.strip() or f"tmp-{uuid4().hex[:8]}"
    materialized = materialize_for_harness(
        profile,
        resolved_skill_sources,
        str(harness),
        resolved_root,
        materialization_chat_id,
        dry_run=request.dry_run,
    )

    command: list[str] = ["claude"]
    if materialized.agent_name:
        command.extend(["--agent", materialized.agent_name])
    command.extend(["--model", str(model)])
    primary_default_tier = resolved_config.primary.permission_tier
    inferred_tier = resolve_permission_tier_from_profile(
        profile=profile,
        default_tier=primary_default_tier,
        warning_logger=logger,
    )
    permission_tier_override = (
        request.permission_tier.strip()
        if request.permission_tier is not None and request.permission_tier.strip()
        else None
    )
    if permission_tier_override is None:
        warn_profile_tier_escalation(
            profile=profile,
            inferred_tier=inferred_tier,
            default_tier=primary_default_tier,
            warning_logger=logger,
        )
    resolved_tier = permission_tier_override or inferred_tier
    # Primary settings only apply to this primary agent launch path.
    # Subagent spawns are assembled in lib/ops/run.py and do not read this config.
    permission_config = build_permission_config(
        resolved_tier,
        unsafe=request.unsafe,
        default_tier=primary_default_tier,
    )
    resolver = build_permission_resolver(
        allowed_tools=profile.allowed_tools if profile is not None else (),
        permission_config=permission_config,
        cli_permission_override=permission_tier_override is not None,
    )
    command.extend(resolver.resolve_flags(harness))
    passthrough_args, passthrough_prompt_fragments = _normalize_system_prompt_passthrough_args(
        passthrough_args
    )
    # Primary space context must always be present in Claude's system prompt.
    # Skill content and passthrough system-prompt fragments are appended as
    # additional sections when available.
    appended_parts = [prompt.strip()]
    appended_parts.extend(fragment.strip() for fragment in passthrough_prompt_fragments if fragment.strip())
    skill_injection = compose_skill_injections(resolved_skills.loaded_skills)
    if skill_injection:
        appended_parts.append(skill_injection)
    command.extend(["--append-system-prompt", "\n\n".join(part for part in appended_parts if part)])
    command.extend(passthrough_args)
    return tuple(command)


def _normalize_system_prompt_passthrough_args(
    passthrough_args: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Extract system-prompt passthroughs and return args without duplicate prompt flags."""

    cleaned: list[str] = []
    prompt_fragments: list[str] = []
    index = 0
    while index < len(passthrough_args):
        token = passthrough_args[index]

        if token in {"--append-system-prompt", "--system-prompt"}:
            if index + 1 >= len(passthrough_args):
                raise ValueError(f"{token} requires a value")
            prompt_fragments.append(passthrough_args[index + 1])
            index += 2
            continue

        if token.startswith("--append-system-prompt="):
            prompt_fragments.append(token.partition("=")[2])
            index += 1
            continue

        if token.startswith("--system-prompt="):
            prompt_fragments.append(token.partition("=")[2])
            index += 1
            continue

        cleaned.append(token)
        index += 1

    return tuple(cleaned), tuple(prompt_fragments)


def _build_harness_command(
    *,
    repo_root: Path,
    request: SpaceLaunchRequest,
    prompt: str,
    chat_id: str = "",
    config: MeridianConfig | None = None,
) -> tuple[str, ...]:
    resolved_config = config if config is not None else load_config(repo_root)
    return _build_interactive_command(
        repo_root=repo_root,
        request=request,
        prompt=prompt,
        passthrough_args=request.passthrough_args,
        chat_id=chat_id,
        config=resolved_config,
    )


def _resolve_primary_session_metadata(
    *,
    repo_root: Path,
    request: SpaceLaunchRequest,
    config: MeridianConfig,
) -> _PrimarySessionMetadata:
    profile = load_agent_profile_with_fallback(
        repo_root=repo_root,
        search_paths=config.search_paths,
        requested_agent=request.agent,
        configured_default=config.default_primary_agent,
        fallback_name="primary",
    )

    defaults = resolve_run_defaults(
        request.model,
        profile=profile,
    )
    model = ModelId(defaults.model)
    harness = _resolve_harness(model=model)

    resolved_skills = resolve_skills_from_profile(
        profile_skills=defaults.skills,
        repo_root=repo_root,
        search_paths=config.search_paths,
        readonly=True,
    )
    if resolved_skills.missing_skills:
        logger.warning(
            "Skipped unavailable skills for primary agent: %s",
            ", ".join(resolved_skills.missing_skills),
        )
    skill_names = resolved_skills.skill_names
    skill_paths = tuple(
        Path(skill.path).expanduser().resolve().as_posix()
        for skill in resolved_skills.loaded_skills
    )

    agent_path = ""
    if profile is not None and profile.path.is_absolute() and profile.path.exists():
        agent_path = profile.path.resolve().as_posix()

    return _PrimarySessionMetadata(
        harness=str(harness),
        model=str(model),
        agent=profile.name if profile is not None else "",
        agent_path=agent_path,
        skills=skill_names,
        skill_paths=skill_paths,
    )


def _resolve_harness(*, model: ModelId) -> HarnessId:
    decision = route_model(str(model), mode="harness")
    harness_id = decision.harness_id
    if harness_id == HarnessId("claude"):
        return harness_id

    message = (
        "Primary agent only supports Claude harness models. "
        f"Model '{model}' routes to harness '{harness_id}'."
    )
    if decision.warning:
        message = f"{message} {decision.warning}"
    raise ValueError(message)


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but owned by another user; assume it's alive.
        return True
    except OSError:
        return False
    return True


def _transition_orphaned_space_states(
    repo_root: Path,
    space_ids: tuple[SpaceId, ...],
) -> None:
    if not space_ids:
        return

    for space_id in space_ids:
        current = space_file.get_space(repo_root, space_id)
        if current is None or current.status != "active":
            continue
        try:
            space_file.update_space_status(repo_root, space_id, "closed")
        except Exception:
            logger.debug("failed to transition orphaned space", exc_info=True)


def cleanup_orphaned_locks(repo_root: Path) -> tuple[SpaceId, ...]:
    """Remove stale space locks and close orphaned active spaces."""

    lock_dir = resolve_state_paths(repo_root).active_spaces_dir
    if not lock_dir.exists():
        return ()

    orphaned: list[SpaceId] = []
    for lock_file in sorted(lock_dir.glob("*.lock")):
        if not lock_file.is_file():
            continue

        space_id = SpaceId(lock_file.stem)
        child_pid = 0
        try:
            parsed = json.loads(lock_file.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                payload = cast("dict[str, object]", parsed)
                raw_space_id = payload.get("space_id")
                if isinstance(raw_space_id, str) and raw_space_id.strip():
                    space_id = SpaceId(raw_space_id.strip())
                raw_child_pid = payload.get("child_pid")
                if isinstance(raw_child_pid, int):
                    child_pid = raw_child_pid
        except (OSError, json.JSONDecodeError, TypeError):
            pass

        if child_pid > 0 and _pid_exists(child_pid):
            continue

        lock_file.unlink(missing_ok=True)
        orphaned.append(space_id)

    deduped = tuple(
        SpaceId(space_id)
        for space_id in sorted({str(space_id) for space_id in orphaned})
    )
    _transition_orphaned_space_states(repo_root, deduped)
    return deduped


def _build_space_env(
    repo_root: Path,
    request: SpaceLaunchRequest,
    prompt: str,
    *,
    default_autocompact_pct: int | None = None,
    spawn_id: str | None = None,
) -> dict[str, str]:
    env_overrides = {
        "MERIDIAN_SPACE_ID": str(request.space_id),
        "MERIDIAN_DEPTH": os.environ.get("MERIDIAN_DEPTH", "0"),
        "MERIDIAN_SPACE_PROMPT": prompt,
        "MERIDIAN_STATE_ROOT": resolve_state_paths(repo_root).root_dir.resolve().as_posix(),
    }
    if spawn_id is not None and spawn_id.strip():
        env_overrides["MERIDIAN_SPAWN_ID"] = spawn_id.strip()
    autocompact_pct = (
        request.autocompact
        if request.autocompact is not None
        else default_autocompact_pct
    )
    if autocompact_pct is not None:
        env_overrides["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] = str(autocompact_pct)

    return sanitize_child_env(
        base_env=os.environ,
        env_overrides=env_overrides,
        pass_through=HARNESS_ENV_PASS_THROUGH,
    )


def _cleanup_launch_materialized(*, repo_root: Path, harness_id: str, chat_id: str) -> None:
    if not harness_id.strip():
        return
    try:
        cleanup_materialized(harness_id, repo_root, chat_id)
    except Exception:
        logger.warning(
            "Failed to cleanup primary-session materialized harness resources "
            "(harness=%s, chat=%s).",
            harness_id,
            chat_id,
            exc_info=True,
        )


def launch_primary(
    *,
    repo_root: Path,
    request: SpaceLaunchRequest,
) -> SpaceLaunchResult:
    """Launch primary agent process and wait for exit."""

    config = load_config(repo_root)
    prompt = build_primary_prompt(request)
    session_metadata = _resolve_primary_session_metadata(
        repo_root=repo_root,
        request=request,
        config=config,
    )
    space_dir = resolve_space_dir(repo_root, request.space_id)
    lock_path = space_lock_path(repo_root, request.space_id)

    if request.dry_run:
        command = _build_harness_command(
            repo_root=repo_root,
            request=request,
            prompt=prompt,
            chat_id="dry-run",
            config=config,
        )
        return SpaceLaunchResult(
            command=command,
            exit_code=0,
            final_state="active",
            lock_path=lock_path,
        )

    command: tuple[str, ...] = ()
    chat_id: str | None = None
    primary_spawn_id: str | None = None
    primary_started = 0.0
    child_env: dict[str, str] | None = None

    # Always use Popen (not execvp) so the finally block can clean up
    # materialized harness files after the child exits.
    exit_code = 2
    process: subprocess.Popen[str] | None = None
    try:
        chat_id = start_session(
            space_dir,
            harness=session_metadata.harness,
            harness_session_id="",
            model=session_metadata.model,
            agent=session_metadata.agent,
            agent_path=session_metadata.agent_path,
            skills=session_metadata.skills,
            skill_paths=session_metadata.skill_paths,
        )
        primary_spawn_id = str(
            spawn_store.start_spawn(
                space_dir,
                chat_id=chat_id,
                model=session_metadata.model,
                agent=session_metadata.agent,
                harness=session_metadata.harness,
                kind="primary",
                prompt=prompt,
            )
        )
        primary_started = time.monotonic()
        child_env = _build_space_env(
            repo_root,
            request,
            prompt,
            default_autocompact_pct=config.primary.autocompact_pct,
            spawn_id=primary_spawn_id,
        )
        command = _build_harness_command(
            repo_root=repo_root,
            request=request,
            prompt=prompt,
            chat_id=chat_id,
            config=config,
        )
        _write_lock(
            path=lock_path,
            space_id=request.space_id,
            command=command,
            child_pid=None,
        )
        process = subprocess.Popen(
            command,
            cwd=repo_root,
            env=child_env,
            text=True,
        )
        _write_lock(
            path=lock_path,
            space_id=request.space_id,
            command=command,
            child_pid=process.pid,
        )

        try:
            exit_code = process.wait()
        except KeyboardInterrupt:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                exit_code = process.wait()
            else:
                exit_code = 130
    except FileNotFoundError:
        exit_code = 2
    finally:
        if primary_spawn_id is not None:
            duration = max(0.0, time.monotonic() - primary_started) if primary_started > 0.0 else None
            spawn_store.finalize_spawn(
                space_dir,
                primary_spawn_id,
                status="succeeded" if exit_code == 0 else "failed",
                exit_code=exit_code,
                duration_secs=duration,
            )
        if chat_id is not None:
            try:
                stop_session(space_dir, chat_id)
            finally:
                _cleanup_launch_materialized(
                    repo_root=repo_root,
                    harness_id=session_metadata.harness,
                    chat_id=chat_id,
                )
        if lock_path.exists():
            lock_path.unlink()

    final_state: SpaceState = "active"
    return SpaceLaunchResult(
        command=command,
        exit_code=exit_code,
        final_state=final_state,
        lock_path=lock_path,
    )

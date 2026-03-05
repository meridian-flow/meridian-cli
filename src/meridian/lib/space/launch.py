"""Primary agent launcher helpers."""

from __future__ import annotations

import json
import logging
import os
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from meridian.lib.config._paths import resolve_repo_root
from meridian.lib.config.routing import route_model
from meridian.lib.config.settings import MeridianConfig, load_config
from meridian.lib.exec.env import (
    HARNESS_ENV_PASS_THROUGH,
    build_harness_child_env,
    sanitize_child_env,
)
from meridian.lib.harness.adapter import HarnessAdapter, SpawnParams
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.harness.materialize import cleanup_materialized, materialize_for_harness
from meridian.lib.harness.session_detection import detect_primary_harness_session_id
from meridian.lib.launch_resolve import (
    load_agent_profile_with_fallback,
    resolve_permission_tier_from_profile,
    resolve_skills_from_profile,
)
from meridian.lib.prompt.assembly import resolve_run_defaults
from meridian.lib.prompt.compose import compose_skill_injections
from meridian.lib.safety.permissions import (
    PermissionConfig,
    build_permission_config,
    build_permission_resolver,
    warn_profile_tier_escalation,
)
from meridian.lib.space.session_store import start_session, stop_session, update_session_harness_id
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
    harness: str | None = None
    agent: str | None = None
    fresh: bool = False
    autocompact: int | None = None
    passthrough_args: tuple[str, ...] = ()
    pinned_context: str = ""
    dry_run: bool = False
    permission_tier: str | None = None
    unsafe: bool = False
    continue_harness_session_id: str | None = None


@dataclass(frozen=True, slots=True)
class SpaceLaunchResult:
    """Result metadata from a completed primary launch."""

    command: tuple[str, ...]
    exit_code: int
    lock_path: Path
    continue_ref: str | None = None


@dataclass(frozen=True, slots=True)
class _PrimarySessionMetadata:
    harness: str
    model: str
    agent: str
    agent_path: str
    skills: tuple[str, ...]
    skill_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _PrimaryHarnessContext:
    command: tuple[str, ...]
    adapter: HarnessAdapter | None = None
    run_params: SpawnParams | None = None
    permission_config: PermissionConfig | None = None


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


def _build_harness_context(
    *,
    repo_root: Path | None = None,
    request: SpaceLaunchRequest,
    prompt: str,
    harness_registry: HarnessRegistry,
    chat_id: str = "",
    config: MeridianConfig | None = None,
) -> _PrimaryHarnessContext:
    """Build primary harness command and launch context for one space session."""

    passthrough_args = request.passthrough_args

    override = os.getenv("MERIDIAN_HARNESS_COMMAND", "").strip()
    if override:
        command = [*shlex.split(override), *passthrough_args]
        if not command:
            raise ValueError("MERIDIAN_HARNESS_COMMAND resolved to an empty command.")
        return _PrimaryHarnessContext(command=tuple(command))

    resolved_root = resolve_repo_root(repo_root)
    resolved_config = config if config is not None else load_config(resolved_root)
    profile = load_agent_profile_with_fallback(
        repo_root=resolved_root,
        search_paths=resolved_config.search_paths,
        requested_agent=request.agent,
        configured_default=resolved_config.default_primary_agent,
        fallback_name="primary",
    )

    default_model = resolved_config.harness.claude
    requested_model = request.model
    if request.harness is not None and request.harness.strip():
        override_default = resolved_config.default_model_for_harness(request.harness)
        if override_default:
            default_model = override_default
            if not requested_model.strip():
                requested_model = override_default

    defaults = resolve_run_defaults(
        requested_model,
        profile=profile,
        default_model=default_model,
    )
    model = ModelId(defaults.model)
    harness = _resolve_harness(
        model=model,
        harness_override=request.harness,
        harness_registry=harness_registry,
        repo_root=resolved_root,
    )
    adapter = harness_registry.get(harness)
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

    passthrough_args, passthrough_prompt_fragments = _normalize_system_prompt_passthrough_args(
        passthrough_args
    )
    harness_session_id = (
        request.continue_harness_session_id.strip()
        if request.continue_harness_session_id is not None
        else ""
    )
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

    appended_parts = [prompt.strip()]
    appended_parts.extend(fragment.strip() for fragment in passthrough_prompt_fragments if fragment.strip())
    skill_injection = compose_skill_injections(resolved_skills.loaded_skills)
    if skill_injection:
        appended_parts.append(skill_injection)
    appended_prompt = "\n\n".join(part for part in appended_parts if part)
    run_params = SpawnParams(
        prompt=appended_prompt,
        model=model,
        skills=resolved_skills.skill_names,
        agent=materialized.agent_name or None,
        extra_args=passthrough_args,
        repo_root=resolved_root.as_posix(),
        mcp_tools=profile.mcp_tools if profile is not None else (),
        interactive=True,
        continue_harness_session_id=harness_session_id or None,
        appended_system_prompt=appended_prompt if appended_prompt else None,
    )
    command = tuple(adapter.build_command(run_params, resolver))
    return _PrimaryHarnessContext(
        command=command,
        adapter=adapter,
        run_params=run_params,
        permission_config=permission_config,
    )


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


def _has_passthrough_session_id(passthrough_args: tuple[str, ...]) -> bool:
    for token in passthrough_args:
        if token == "--session-id" or token.startswith("--session-id="):
            return True
    return False


def _build_harness_command(
    *,
    repo_root: Path,
    request: SpaceLaunchRequest,
    prompt: str,
    harness_registry: HarnessRegistry,
    chat_id: str = "",
    config: MeridianConfig | None = None,
) -> tuple[str, ...]:
    resolved_config = config if config is not None else load_config(repo_root)
    return _build_harness_context(
        repo_root=repo_root,
        request=request,
        prompt=prompt,
        harness_registry=harness_registry,
        chat_id=chat_id,
        config=resolved_config,
    ).command


def _resolve_primary_session_metadata(
    *,
    repo_root: Path,
    request: SpaceLaunchRequest,
    config: MeridianConfig,
    harness_registry: HarnessRegistry,
) -> _PrimarySessionMetadata:
    profile = load_agent_profile_with_fallback(
        repo_root=repo_root,
        search_paths=config.search_paths,
        requested_agent=request.agent,
        configured_default=config.default_primary_agent,
        fallback_name="primary",
    )

    default_model = config.harness.claude
    requested_model = request.model
    if request.harness is not None and request.harness.strip():
        override_default = config.default_model_for_harness(request.harness)
        if override_default:
            default_model = override_default
            if not requested_model.strip():
                requested_model = override_default

    defaults = resolve_run_defaults(
        requested_model,
        profile=profile,
        default_model=default_model,
    )
    model = ModelId(defaults.model)
    harness = _resolve_harness(
        model=model,
        harness_override=request.harness,
        harness_registry=harness_registry,
        repo_root=repo_root,
    )

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


def _resolve_harness(
    *,
    model: ModelId,
    harness_override: str | None,
    harness_registry: HarnessRegistry,
    repo_root: Path,
) -> HarnessId:
    warning: str | None = None
    from meridian.lib.config.catalog import resolve_model

    try:
        resolved = resolve_model(str(model), repo_root=repo_root)
        routed_harness_id = resolved.harness
    except KeyError:
        decision = route_model(str(model), mode="harness")
        routed_harness_id = decision.harness_id
        warning = decision.warning
    supported_primary_harnesses = tuple(
        harness_id
        for harness_id in harness_registry.ids()
        if harness_registry.get(harness_id).capabilities.supports_primary_launch
    )
    supported_primary_set = set(supported_primary_harnesses)

    normalized_override = (harness_override or "").strip()
    if not normalized_override:
        return routed_harness_id

    override_harness = HarnessId(normalized_override)
    if override_harness not in supported_primary_set:
        supported_text = ", ".join(str(harness_id) for harness_id in supported_primary_harnesses)
        raise ValueError(
            f"Unsupported harness '{normalized_override}'. "
            f"Expected one of: {supported_text}."
        )
    if override_harness != routed_harness_id:
        message = (
            f"Harness '{override_harness}' is incompatible with model '{model}' "
            f"(routes to '{routed_harness_id}')."
        )
        if warning:
            message = f"{message} {warning}"
        raise ValueError(message)
    return override_harness


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


def cleanup_orphaned_locks(repo_root: Path) -> tuple[SpaceId, ...]:
    """Remove stale space locks."""

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
            logger.debug("Failed to parse lock file %s", lock_file, exc_info=True)

        if child_pid > 0 and _pid_exists(child_pid):
            continue

        lock_file.unlink(missing_ok=True)
        orphaned.append(space_id)

    deduped = tuple(
        SpaceId(space_id)
        for space_id in sorted({str(space_id) for space_id in orphaned})
    )
    return deduped


def _build_space_env(
    repo_root: Path,
    request: SpaceLaunchRequest,
    prompt: str,
    *,
    default_autocompact_pct: int | None = None,
    spawn_id: str | None = None,
    harness_context: _PrimaryHarnessContext | None = None,
) -> dict[str, str]:
    env_overrides = {
        "MERIDIAN_SPACE_ID": str(request.space_id),
        "MERIDIAN_DEPTH": os.environ.get("MERIDIAN_DEPTH", "0"),
        "MERIDIAN_REPO_ROOT": repo_root.as_posix(),
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

    if (
        harness_context is not None
        and harness_context.adapter is not None
        and harness_context.run_params is not None
        and harness_context.permission_config is not None
    ):
        return build_harness_child_env(
            base_env=os.environ,
            adapter=harness_context.adapter,
            run_params=harness_context.run_params,
            permission_config=harness_context.permission_config,
            runtime_env_overrides=env_overrides,
            pass_through=HARNESS_ENV_PASS_THROUGH,
        )

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


@dataclass(frozen=True, slots=True)
class _LaunchContext:
    """Resolved configuration for one primary launch."""

    config: MeridianConfig
    prompt: str
    session_metadata: _PrimarySessionMetadata
    space_dir: Path
    lock_path: Path
    seed_harness_session_id: str
    command_request: SpaceLaunchRequest


@dataclass(frozen=True, slots=True)
class _ProcessOutcome:
    """Result of running the harness subprocess."""

    command: tuple[str, ...]
    exit_code: int
    chat_id: str | None
    primary_spawn_id: str | None
    primary_started: float
    primary_started_epoch: float
    primary_started_local_iso: str | None
    resolved_harness_session_id: str


def _prepare_launch_context(
    repo_root: Path,
    request: SpaceLaunchRequest,
    harness_registry: HarnessRegistry,
) -> _LaunchContext:
    """Config loading, prompt building, session-ID seeding, command-request patching."""

    config = load_config(repo_root)
    prompt = build_primary_prompt(request)
    session_metadata = _resolve_primary_session_metadata(
        repo_root=repo_root,
        request=request,
        config=config,
        harness_registry=harness_registry,
    )
    space_dir = resolve_space_dir(repo_root, request.space_id)
    lock_path = space_lock_path(repo_root, request.space_id)

    explicit_session_id = (
        request.continue_harness_session_id.strip()
        if request.continue_harness_session_id is not None
        else ""
    )
    is_claude = session_metadata.harness == "claude"
    seed_harness_session_id = explicit_session_id or (str(uuid4()) if is_claude else "")
    command_request = request
    if (
        is_claude
        and seed_harness_session_id
        and not explicit_session_id
        and not _has_passthrough_session_id(request.passthrough_args)
    ):
        command_request = replace(
            request,
            passthrough_args=(
                *request.passthrough_args,
                "--session-id",
                seed_harness_session_id,
            ),
        )

    return _LaunchContext(
        config=config,
        prompt=prompt,
        session_metadata=session_metadata,
        space_dir=space_dir,
        lock_path=lock_path,
        seed_harness_session_id=seed_harness_session_id,
        command_request=command_request,
    )


def _run_harness_process(
    repo_root: Path,
    request: SpaceLaunchRequest,
    ctx: _LaunchContext,
    harness_registry: HarnessRegistry,
) -> _ProcessOutcome:
    """Start session, spawn tracking, launch process, wait for exit."""

    command: tuple[str, ...] = ()
    chat_id: str | None = None
    primary_spawn_id: str | None = None
    primary_started = 0.0
    primary_started_epoch = 0.0
    primary_started_local_iso: str | None = None
    resolved_harness_session_id = ctx.seed_harness_session_id

    # Always use Popen (not execvp) so the finally block can clean up
    # materialized harness files after the child exits.
    exit_code = 2
    try:
        chat_id = start_session(
            ctx.space_dir,
            harness=ctx.session_metadata.harness,
            harness_session_id=ctx.seed_harness_session_id,
            model=ctx.session_metadata.model,
            agent=ctx.session_metadata.agent,
            agent_path=ctx.session_metadata.agent_path,
            skills=ctx.session_metadata.skills,
            skill_paths=ctx.session_metadata.skill_paths,
        )
        primary_spawn_id = str(
            spawn_store.start_spawn(
                ctx.space_dir,
                chat_id=chat_id,
                model=ctx.session_metadata.model,
                agent=ctx.session_metadata.agent,
                harness=ctx.session_metadata.harness,
                kind="primary",
                prompt=ctx.prompt,
            )
        )
        primary_started = time.monotonic()
        primary_started_epoch = time.time()
        primary_started_local_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        harness_context = _build_harness_context(
            repo_root=repo_root,
            request=ctx.command_request,
            prompt=ctx.prompt,
            harness_registry=harness_registry,
            chat_id=chat_id,
            config=ctx.config,
        )
        command = harness_context.command
        child_env = _build_space_env(
            repo_root,
            request,
            ctx.prompt,
            default_autocompact_pct=ctx.config.primary.autocompact_pct,
            spawn_id=primary_spawn_id,
            harness_context=harness_context,
        )
        _write_lock(
            path=ctx.lock_path,
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
            path=ctx.lock_path,
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
        logger.debug("Harness command not found", exc_info=True)
        exit_code = 2
    finally:
        if primary_spawn_id is not None:
            duration = max(0.0, time.monotonic() - primary_started) if primary_started > 0.0 else None
            spawn_store.finalize_spawn(
                ctx.space_dir,
                primary_spawn_id,
                status="succeeded" if exit_code == 0 else "failed",
                exit_code=exit_code,
                duration_secs=duration,
            )
        if chat_id is not None:
            try:
                observed_harness_session_id = None
                if primary_started_epoch > 0.0:
                    observed_harness_session_id = detect_primary_harness_session_id(
                        harness_id=ctx.session_metadata.harness,
                        repo_root=repo_root,
                        started_at_epoch=primary_started_epoch,
                        started_at_local_iso=primary_started_local_iso,
                    )
                if (
                    observed_harness_session_id is not None
                    and observed_harness_session_id.strip()
                    and observed_harness_session_id.strip() != resolved_harness_session_id.strip()
                ):
                    resolved_harness_session_id = observed_harness_session_id.strip()
                    update_session_harness_id(ctx.space_dir, chat_id, resolved_harness_session_id)
                stop_session(ctx.space_dir, chat_id)
            finally:
                _cleanup_launch_materialized(
                    repo_root=repo_root,
                    harness_id=ctx.session_metadata.harness,
                    chat_id=chat_id,
                )
        try:
            if ctx.lock_path.exists():
                ctx.lock_path.unlink()
        except OSError:
            logger.debug("Failed to clean up lock file %s", ctx.lock_path, exc_info=True)

    return _ProcessOutcome(
        command=command,
        exit_code=exit_code,
        chat_id=chat_id,
        primary_spawn_id=primary_spawn_id,
        primary_started=primary_started,
        primary_started_epoch=primary_started_epoch,
        primary_started_local_iso=primary_started_local_iso,
        resolved_harness_session_id=resolved_harness_session_id,
    )


def launch_primary(
    *,
    repo_root: Path,
    request: SpaceLaunchRequest,
    harness_registry: HarnessRegistry,
) -> SpaceLaunchResult:
    """Launch primary agent process and wait for exit."""

    ctx = _prepare_launch_context(repo_root, request, harness_registry)

    if request.dry_run:
        command = _build_harness_command(
            repo_root=repo_root,
            request=request,
            prompt=ctx.prompt,
            harness_registry=harness_registry,
            chat_id="dry-run",
            config=ctx.config,
        )
        return SpaceLaunchResult(
            command=command,
            exit_code=0,
            lock_path=ctx.lock_path,
            continue_ref=None,
        )

    outcome = _run_harness_process(repo_root, request, ctx, harness_registry)
    continue_ref = outcome.resolved_harness_session_id.strip() or None

    return SpaceLaunchResult(
        command=outcome.command,
        exit_code=outcome.exit_code,
        lock_path=ctx.lock_path,
        continue_ref=continue_ref,
    )

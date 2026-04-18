"""Headless runner for Phase-1 streaming spawn integration."""

from __future__ import annotations

import time
from uuid import uuid4

from meridian.lib.core.domain import SpawnStatus
from meridian.lib.core.types import HarnessId
from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch.context import build_launch_context
from meridian.lib.launch.request import LaunchArgvIntent, LaunchRuntime, SpawnRequest
from meridian.lib.launch.streaming_runner import run_streaming_spawn, signal_coordinator
from meridian.lib.ops.runtime import resolve_runtime_root_and_config, resolve_state_root
from meridian.lib.state import spawn_store


async def streaming_serve(
    harness: str,
    prompt: str,
    model: str | None = None,
    agent: str | None = None,
    debug: bool = False,
) -> None:
    """Start a bidirectional spawn and keep it running until completion."""

    normalized_harness = harness.strip().lower()
    if not normalized_harness:
        raise ValueError("harness is required")
    normalized_prompt = prompt.strip()
    if not normalized_prompt:
        raise ValueError("prompt is required")
    normalized_model = model.strip() if model is not None else None
    if model is not None and not normalized_model:
        raise ValueError("model cannot be empty")
    normalized_agent = agent.strip() if agent is not None else None

    try:
        harness_id = HarnessId(normalized_harness)
    except ValueError as exc:
        supported = ", ".join(item.value for item in HarnessId)
        raise ValueError(f"unsupported harness '{harness}'. Supported: {supported}") from exc

    repo_root, _ = resolve_runtime_root_and_config(None)
    state_root = resolve_state_root(repo_root)
    start_monotonic = time.monotonic()
    spawn_id = spawn_store.start_spawn(
        state_root,
        chat_id=str(uuid4()),
        model=normalized_model or "unknown",
        agent=normalized_agent or "unknown",
        harness=harness_id.value,
        kind="streaming",
        prompt=prompt,
        launch_mode="foreground",
        status="running",
    )

    tracer = None
    if debug:
        from meridian.lib.observability.debug_tracer import DebugTracer

        spawn_dir = state_root / "spawns" / str(spawn_id)
        tracer = DebugTracer(
            spawn_id=str(spawn_id),
            debug_path=spawn_dir / "debug.jsonl",
            echo_stderr=True,
        )

    config = ConnectionConfig(
        spawn_id=spawn_id,
        harness_id=harness_id,
        prompt=prompt,
        repo_root=repo_root,
        env_overrides={},
        debug_tracer=tracer,
    )

    # I-2: route spec resolution through the factory rather than constructing
    # permission resolvers or calling adapter.resolve_launch_spec() directly.
    spawn_req = SpawnRequest(
        prompt=normalized_prompt,
        model=normalized_model,
        harness=harness_id.value,
        agent=normalized_agent,
    )
    launch_runtime = LaunchRuntime(
        argv_intent=LaunchArgvIntent.SPEC_ONLY,
        state_root=state_root.as_posix(),
        project_paths_repo_root=repo_root.as_posix(),
        project_paths_execution_cwd=repo_root.as_posix(),
    )
    launch_ctx = build_launch_context(
        spawn_id=str(spawn_id),
        request=spawn_req,
        runtime=launch_runtime,
        harness_registry=get_default_harness_registry(),
    )

    output_path = state_root / "spawns" / str(spawn_id) / "output.jsonl"
    socket_path = state_root / "spawns" / str(spawn_id) / "control.sock"

    print(f"Started spawn {spawn_id} (harness={harness_id.value})")
    print(f"Control socket: {socket_path}")
    print(f"Events: {output_path}")

    outcome_status: SpawnStatus = "failed"
    outcome_exit_code = 1
    failure_message: str | None = None
    try:
        outcome = await run_streaming_spawn(
            config=config,
            spec=launch_ctx.spec,
            state_root=state_root,
            repo_root=repo_root,
            spawn_id=spawn_id,
        )
        outcome_status = outcome.status
        outcome_exit_code = outcome.exit_code
        if outcome_status == "failed":
            failure_message = outcome.error
    except Exception as exc:
        failure_message = str(exc)
        raise
    finally:
        with signal_coordinator().mask_sigterm():
            spawn_store.finalize_spawn(
                state_root,
                spawn_id,
                status=outcome_status,
                exit_code=outcome_exit_code,
                origin="launcher",
                duration_secs=max(0.0, time.monotonic() - start_monotonic),
                error=failure_message if outcome_status == "failed" else None,
            )
            print(f"Stopped spawn {spawn_id} (status={outcome_status}, exit={outcome_exit_code})")

"""Headless runner for Phase-1 streaming spawn integration."""

from __future__ import annotations

import asyncio
import signal
import time
from collections.abc import Iterable
from uuid import uuid4

from meridian.lib.core.domain import SpawnStatus
from meridian.lib.core.types import HarnessId
from meridian.lib.harness.connections.base import ConnectionConfig, HarnessEvent
from meridian.lib.ops.runtime import resolve_runtime_root_and_config
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.streaming.spawn_manager import SpawnManager


def _install_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    shutdown_event: asyncio.Event,
) -> list[signal.Signals]:
    installed: list[signal.Signals] = []
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown_event.set)
            installed.append(sig)
        except (NotImplementedError, RuntimeError):
            continue
    return installed


def _remove_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    signals: Iterable[signal.Signals],
) -> None:
    for sig in signals:
        try:
            loop.remove_signal_handler(sig)
        except Exception:
            continue


async def _wait_for_connection_close(
    queue: asyncio.Queue[HarnessEvent | None],
) -> str:
    while True:
        event = await queue.get()
        if event is None:
            return "connection_closed"


async def _wait_for_shutdown(shutdown_event: asyncio.Event) -> str:
    await shutdown_event.wait()
    return "shutdown_requested"


async def streaming_serve(
    harness: str,
    prompt: str,
    model: str | None = None,
    agent: str | None = None,
) -> None:
    """Start a bidirectional spawn and keep it running until completion."""

    normalized_harness = harness.strip().lower()
    if not normalized_harness:
        raise ValueError("harness is required")

    try:
        harness_id = HarnessId(normalized_harness)
    except ValueError as exc:
        supported = ", ".join(item.value for item in HarnessId if item != HarnessId.DIRECT)
        raise ValueError(f"unsupported harness '{harness}'. Supported: {supported}") from exc

    repo_root, _ = resolve_runtime_root_and_config(None)
    state_paths = resolve_state_paths(repo_root)
    state_root = state_paths.root_dir
    start_monotonic = time.monotonic()
    spawn_id = spawn_store.start_spawn(
        state_root,
        chat_id=str(uuid4()),
        model=(model.strip() if model is not None else "") or "unknown",
        agent=(agent.strip() if agent is not None else "") or "unknown",
        harness=harness_id.value,
        kind="streaming",
        prompt=prompt,
        launch_mode="foreground",
        status="running",
    )

    manager = SpawnManager(state_root=state_root, repo_root=repo_root)
    config = ConnectionConfig(
        spawn_id=spawn_id,
        harness_id=harness_id,
        model=(model.strip() or None) if model is not None else None,
        agent=(agent.strip() or None) if agent is not None else None,
        prompt=prompt,
        repo_root=repo_root,
        env_overrides={},
    )

    output_path = state_root / "spawns" / str(spawn_id) / "output.jsonl"
    socket_path = state_root / "spawns" / str(spawn_id) / "control.sock"

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    installed_signals = _install_signal_handlers(loop, shutdown_event)

    terminal_reason = "shutdown_requested"
    had_error = False
    failure_message: str | None = None
    manager_started = False
    completion_task: asyncio.Task[str] | None = None
    shutdown_task: asyncio.Task[str] | None = None
    try:
        await manager.start_spawn(config)
        manager_started = True
        print(f"Started spawn {spawn_id} (harness={harness_id.value})")
        print(f"Control socket: {socket_path}")
        print(f"Events: {output_path}")

        subscriber = manager.subscribe(spawn_id)
        if subscriber is None:
            raise RuntimeError("failed to attach spawn event subscriber")

        completion_task = asyncio.create_task(_wait_for_connection_close(subscriber))
        shutdown_task = asyncio.create_task(_wait_for_shutdown(shutdown_event))

        done, pending = await asyncio.wait(
            (completion_task, shutdown_task),
            return_when=asyncio.FIRST_COMPLETED,
        )
        for pending_task in pending:
            pending_task.cancel()

        terminal_reason = next(iter(done)).result()
    except KeyboardInterrupt:
        terminal_reason = "keyboard_interrupt"
        had_error = True
        failure_message = "keyboard interrupt"
    except Exception as exc:
        had_error = True
        failure_message = str(exc)
        raise
    finally:
        if completion_task is not None and not completion_task.done():
            completion_task.cancel()
        if shutdown_task is not None and not shutdown_task.done():
            shutdown_task.cancel()
        manager.unsubscribe(spawn_id)
        _remove_signal_handlers(loop, installed_signals)
        shutdown_status: SpawnStatus = "cancelled"
        shutdown_exit_code = 1
        if terminal_reason == "connection_closed" and not had_error:
            shutdown_status = "succeeded"
            shutdown_exit_code = 0
        elif had_error:
            shutdown_status = "failed"
        await manager.shutdown(
            status=shutdown_status,
            exit_code=shutdown_exit_code,
            error=failure_message,
        )
        if not manager_started:
            spawn_store.finalize_spawn(
                state_root,
                spawn_id,
                status=shutdown_status,
                exit_code=shutdown_exit_code,
                duration_secs=max(0.0, time.monotonic() - start_monotonic),
                error=failure_message if shutdown_status == "failed" else None,
            )
        print(f"Stopped spawn {spawn_id} ({terminal_reason})")

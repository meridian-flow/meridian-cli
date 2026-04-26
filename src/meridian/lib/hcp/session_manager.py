"""HCP chat lifecycle ownership built on SpawnManager."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping
from pathlib import Path

from meridian.lib.core.lifecycle import SpawnLifecycleService, create_lifecycle_service
from meridian.lib.core.spawn_service import SpawnApplicationService
from meridian.lib.core.types import SpawnId
from meridian.lib.harness.connections.base import ConnectionConfig, HarnessEvent
from meridian.lib.launch.launch_types import ResolvedLaunchSpec
from meridian.lib.state import session_store, spawn_store
from meridian.lib.state.atomic import append_text_line
from meridian.lib.state.paths import RuntimePaths
from meridian.lib.streaming.drain_policy import PersistentDrainPolicy
from meridian.lib.streaming.spawn_manager import SpawnManager

from .errors import HcpError, HcpErrorCategory
from .types import ChatState


class HcpSessionManager:
    def __init__(
        self,
        spawn_manager: SpawnManager,
        runtime_root: Path,
        idle_timeout_secs: float = 3600.0,
        lifecycle_service: SpawnLifecycleService | None = None,
    ) -> None:
        self._spawn_manager = spawn_manager
        self._runtime_root = runtime_root
        self._lifecycle_service = lifecycle_service or create_lifecycle_service(
            spawn_manager.project_root,
            runtime_root,
        )
        self._spawn_service = SpawnApplicationService(
            runtime_root,
            self._lifecycle_service,
            spawn_manager=spawn_manager,
        )
        self._idle_timeout = idle_timeout_secs
        self._active_processes: dict[str, SpawnId] = {}
        self._chat_states: dict[str, ChatState] = {}
        self._chat_mutexes: dict[str, asyncio.Lock] = {}
        self._idle_timers: dict[str, asyncio.Task[None]] = {}

    async def restore_from_stores(self) -> None:
        """Restore known primary chats from the session store as idle."""

        records = session_store.list_active_session_records(self._runtime_root)
        for record in records:
            if record.kind != "primary":
                continue
            self._chat_states[record.chat_id] = ChatState.IDLE
            self._chat_mutexes.setdefault(record.chat_id, asyncio.Lock())
            await self._write_lifecycle_event(
                record.chat_id,
                "state_change",
                {"state": ChatState.IDLE.value, "source": "restore"},
            )

    async def create_chat(
        self,
        prompt: str,
        model: str | None = None,
        harness: str = "claude",
        *,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
        agent: str = "",
        agent_path: str = "",
        skills: tuple[str, ...] = (),
        skill_paths: tuple[str, ...] = (),
        params: tuple[str, ...] = (),
        harness_session_id: str = "",
        execution_cwd: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> tuple[str, SpawnId]:
        """Create a primary chat and launch its persistent harness process."""

        resolved_model = model or "unknown"
        c_id = session_store.start_session(
            self._runtime_root,
            harness=harness,
            harness_session_id=harness_session_id,
            model=resolved_model,
            params=params,
            agent=agent,
            agent_path=agent_path,
            skills=skills,
            skill_paths=skill_paths,
            execution_cwd=execution_cwd,
            kind="primary",
        )
        p_id = SpawnId(
            self._lifecycle_service.start(
                chat_id=c_id,
                model=resolved_model,
                agent=agent,
                agent_path=agent_path or None,
                skills=skills,
                skill_paths=skill_paths,
                harness=harness,
                kind="hcp",
                prompt=prompt,
                spawn_id=config.spawn_id,
                harness_session_id=harness_session_id or None,
                execution_cwd=execution_cwd,
                launch_mode="app",
            )
        )
        self._active_processes[c_id] = p_id
        self._chat_states[c_id] = ChatState.ACTIVE
        self._chat_mutexes.setdefault(c_id, asyncio.Lock())
        await self._write_lifecycle_event(
            c_id,
            "state_change",
            {
                "state": ChatState.ACTIVE.value,
                "p_id": str(p_id),
                "metadata": dict(metadata or {}),
            },
        )
        try:
            connection = await self._spawn_manager.start_spawn(
                config,
                spec,
                drain_policy=PersistentDrainPolicy(),
                on_event=lambda event: self._capture_harness_session_id(c_id, p_id, event),
            )
            connection_session_id = getattr(connection, "session_id", None)
            if isinstance(connection_session_id, str) and connection_session_id.strip():
                self._persist_harness_session_id(c_id, p_id, connection_session_id)
            await self._spawn_manager._start_heartbeat(p_id)  # pyright: ignore[reportPrivateUsage]
        except Exception:
            self._active_processes.pop(c_id, None)
            self._chat_states[c_id] = ChatState.IDLE
            await self._spawn_service.complete_spawn(
                p_id,
                "failed",
                1,
                origin="launch_failure",
            )
            session_store.stop_session(self._runtime_root, c_id)
            await self._write_lifecycle_event(
                c_id,
                "state_change",
                {"state": ChatState.IDLE.value, "source": "launch_failed"},
            )
            raise
        self._reset_idle_timer(c_id)
        return c_id, p_id

    def _capture_harness_session_id(
        self,
        c_id: str,
        p_id: SpawnId,
        event: HarnessEvent,
    ) -> None:
        """Persist a harness session ID discovered from stream events."""

        for key in ("session_id", "sessionId"):
            value = event.payload.get(key)
            if isinstance(value, str) and value.strip():
                self._persist_harness_session_id(c_id, p_id, value)
                return

    def _persist_harness_session_id(
        self,
        c_id: str,
        p_id: SpawnId,
        harness_session_id: str,
    ) -> None:
        normalized = harness_session_id.strip()
        if not normalized:
            return
        session_store.update_session_harness_id(self._runtime_root, c_id, normalized)
        spawn_store.update_spawn(
            self._runtime_root,
            p_id,
            harness_session_id=normalized,
        )

    async def prompt(self, c_id: str, text: str) -> None:
        """Send a user message to an active chat."""

        lock = self._chat_mutexes.setdefault(c_id, asyncio.Lock())
        if lock.locked():
            raise HcpError(
                HcpErrorCategory.CONCURRENT_PROMPT,
                f"chat {c_id} already has an active prompt",
            )
        async with lock:
            p_id = self._active_processes.get(c_id)
            if p_id is None:
                raise HcpError(
                    HcpErrorCategory.RESUME_FAILED,
                    f"chat {c_id} has no active process",
                )
            self._chat_states[c_id] = ChatState.ACTIVE
            await self._write_lifecycle_event(
                c_id,
                "state_change",
                {"state": ChatState.ACTIVE.value, "reason": "prompt"},
            )
            result = await self._spawn_manager.inject(p_id, text, source="hcp")
            if not result.success:
                self._active_processes.pop(c_id, None)
                self._chat_states[c_id] = ChatState.IDLE
                await self._write_lifecycle_event(
                    c_id,
                    "state_change",
                    {"state": ChatState.IDLE.value, "reason": "inject_failed"},
                )
                raise HcpError(
                    HcpErrorCategory.HARNESS_CRASHED,
                    result.error or f"failed to prompt chat {c_id}",
                )
            self._reset_idle_timer(c_id)

    async def cancel(self, c_id: str) -> None:
        """Cancel the current turn for a chat."""

        p_id = self._active_processes.get(c_id)
        if p_id is None:
            return
        self._chat_states[c_id] = ChatState.DRAINING
        await self._write_lifecycle_event(
            c_id,
            "state_change",
            {"state": ChatState.DRAINING.value, "reason": "cancel"},
        )
        await self._spawn_manager.stop_spawn(p_id, status="cancelled", exit_code=143)
        self._active_processes.pop(c_id, None)
        self._chat_states[c_id] = ChatState.IDLE
        await self._write_lifecycle_event(
            c_id,
            "state_change",
            {"state": ChatState.IDLE.value, "reason": "cancelled"},
        )

    async def close_chat(self, c_id: str) -> None:
        """Close a chat session and stop its active process, if any."""

        timer = self._idle_timers.pop(c_id, None)
        if timer is not None:
            timer.cancel()
        p_id = self._active_processes.pop(c_id, None)
        if p_id is not None:
            await self._spawn_manager.stop_spawn(p_id, status="cancelled", exit_code=143)
        session_store.stop_session(self._runtime_root, c_id)
        self._chat_states[c_id] = ChatState.CLOSED
        await self._write_lifecycle_event(
            c_id,
            "state_change",
            {"state": ChatState.CLOSED.value},
        )

    async def shutdown(self) -> None:
        """Cancel all idle timers."""

        for task in self._idle_timers.values():
            task.cancel()
        self._idle_timers.clear()

    def get_chat_state(self, c_id: str) -> ChatState | None:
        return self._chat_states.get(c_id)

    def get_active_p_id(self, c_id: str) -> SpawnId | None:
        return self._active_processes.get(c_id)

    async def _write_lifecycle_event(
        self,
        c_id: str,
        event: str,
        data: Mapping[str, object] | None = None,
    ) -> None:
        """Write one lifecycle event to chats/<c_id>/lifecycle.jsonl."""

        paths = RuntimePaths.from_root_dir(self._runtime_root)
        lifecycle_path = paths.chat_lifecycle_path(c_id)
        lifecycle_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "event": event,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "data": dict(data or {}),
        }
        await asyncio.to_thread(
            append_text_line,
            lifecycle_path,
            json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n",
        )

    def _reset_idle_timer(self, c_id: str) -> None:
        timer = self._idle_timers.pop(c_id, None)
        if timer is not None:
            timer.cancel()
        self._idle_timers[c_id] = asyncio.create_task(self._idle_after_timeout(c_id))

    async def _idle_after_timeout(self, c_id: str) -> None:
        try:
            await asyncio.sleep(self._idle_timeout)
            if self._chat_states.get(c_id) == ChatState.ACTIVE:
                self._chat_states[c_id] = ChatState.IDLE
                await self._write_lifecycle_event(
                    c_id,
                    "state_change",
                    {"state": ChatState.IDLE.value, "reason": "idle_timeout"},
                )
        except asyncio.CancelledError:
            raise


__all__ = ["HcpSessionManager"]

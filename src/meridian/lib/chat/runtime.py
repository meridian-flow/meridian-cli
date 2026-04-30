"""Runtime registry for headless chat sessions."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol
from uuid import uuid4

from meridian.lib.chat.backend_acquisition import BackendAcquisition, BackendAcquisitionFactory
from meridian.lib.chat.checkpoint import CheckpointService
from meridian.lib.chat.command_handler import ChatCommandHandler
from meridian.lib.chat.commands import COMMAND_CLOSE, ChatCommand, CommandResult
from meridian.lib.chat.event_index import ChatEventIndex
from meridian.lib.chat.event_log import ChatEventLog
from meridian.lib.chat.event_pipeline import ChatEventPipeline
from meridian.lib.chat.protocol import CHAT_EXITED, CHAT_STARTED, ChatEvent, utc_now_iso
from meridian.lib.chat.session_service import ChatSessionService
from meridian.lib.chat.ws_fanout import WebSocketFanOut
from meridian.lib.state.paths import RuntimePaths


@dataclass
class LiveChatEntry:
    session: ChatSessionService
    event_log: ChatEventLog
    event_index: ChatEventIndex
    fanout: WebSocketFanOut | None
    pipeline: ChatEventPipeline
    checkpoint: CheckpointService


@dataclass(frozen=True)
class PersistedChatRecord:
    event_log: ChatEventLog
    event_index: ChatEventIndex
    state: Literal["closed"]


@dataclass(frozen=True)
class ChatRuntimeView:
    chat_id: str
    state: str


@dataclass(frozen=True)
class ChatStreamSource:
    event_log: ChatEventLog
    fanout: WebSocketFanOut | None


class PipelineLookup(Protocol):
    """Lookup seam for acquisition code that needs an existing live pipeline."""

    def get_pipeline(self, chat_id: str) -> ChatEventPipeline | None: ...


class ChatRuntime(PipelineLookup):
    """Own recovered chat state and live chat service registries."""

    def __init__(
        self,
        *,
        runtime_root: Path,
        project_root: Path,
        backend_acquisition: BackendAcquisition | None = None,
        acquisition_factory: BackendAcquisitionFactory | None = None,
    ) -> None:
        self.runtime_root = runtime_root
        self.project_root = project_root
        self.paths = RuntimePaths.from_root_dir(runtime_root)
        self.checkpoint_lock = asyncio.Lock()
        self._live: dict[str, LiveChatEntry] = {}
        self._persisted_only: dict[str, PersistedChatRecord] = {}
        self._started = False
        self._stopped = False
        if acquisition_factory is not None:
            self.backend_acquisition = acquisition_factory.build(
                pipeline_lookup=self,
                project_root=project_root,
                runtime_root=runtime_root,
            )
        elif backend_acquisition is not None:
            self.backend_acquisition = backend_acquisition
        else:
            raise ValueError("backend_acquisition or acquisition_factory is required")

    @property
    def live_entries(self) -> dict[str, LiveChatEntry]:
        return self._live

    @property
    def persisted_only(self) -> dict[str, PersistedChatRecord]:
        return self._persisted_only

    async def start(self) -> None:
        """Recover chats from disk and start live pipelines."""

        self._ensure_running()
        if not self._started:
            from meridian.lib.chat.recovery import recover_all

            recovered = recover_all(
                paths=self.paths,
                project_root=self.project_root,
                backend_acquisition=self.backend_acquisition,
                checkpoint_lock=self.checkpoint_lock,
                active_chat_counter=self.active_chat_count,
            )
            self._live.update(
                {
                    chat_id: entry
                    for chat_id, entry in recovered.live_entries.items()
                    if chat_id not in self._live
                }
            )
            self._persisted_only.update(
                {
                    chat_id: record
                    for chat_id, record in recovered.persisted_only.items()
                    if chat_id not in self._persisted_only and chat_id not in self._live
                }
            )
            self._started = True

        for entry in self._live.values():
            entry.pipeline.start()

    async def stop(self) -> None:
        """Stop live runtime resources without writing chat lifecycle events."""

        if self._stopped:
            return
        self._stopped = True
        try:
            for entry in list(self._live.values()):
                handle = entry.session.current_execution
                if handle is not None:
                    with suppress(Exception):
                        await handle.stop()
                with suppress(Exception):
                    await entry.pipeline.drain()
                with suppress(Exception):
                    await entry.pipeline.stop()
                entry.fanout = None
            self._live.clear()
            self._persisted_only.clear()
        finally:
            self._started = False
            self._stopped = False

    async def create_chat(self) -> ChatRuntimeView:
        """Create a new chat, register it live, start its pipeline, emit chat.started."""

        self._ensure_running()
        chat_id = f"c-{uuid4().hex}"
        event_log = ChatEventLog(self.paths.chat_history_path(chat_id))
        event_index = ChatEventIndex(self.paths.chats_dir / chat_id / "index.sqlite3")
        entry = build_live_entry(
            chat_id=chat_id,
            event_log=event_log,
            event_index=event_index,
            backend_acquisition=self.backend_acquisition,
            project_root=self.project_root,
            checkpoint_lock=self.checkpoint_lock,
            active_chat_counter=self.active_chat_count,
        )
        entry.pipeline.start()
        self.register_live(chat_id, entry)

        await entry.pipeline.ingest(
            ChatEvent(
                type=CHAT_STARTED,
                seq=0,
                chat_id=chat_id,
                execution_id="",
                timestamp=utc_now_iso(),
            )
        )
        await entry.pipeline.drain()
        return ChatRuntimeView(chat_id=chat_id, state=entry.session.state)

    async def dispatch(self, command: ChatCommand) -> CommandResult:
        """Dispatch an inbound command and own runtime-level accepted close postwork."""

        self._ensure_running()
        handler = ChatCommandHandler(
            {chat_id: entry.session for chat_id, entry in self._live.items()},
            {chat_id: entry.pipeline for chat_id, entry in self._live.items()},
            {chat_id: entry.checkpoint for chat_id, entry in self._live.items()},
        )
        result = await handler.dispatch(command)
        if command.type == COMMAND_CLOSE and result.status == "accepted":
            entry = self._live.get(command.chat_id)
            if entry is not None:
                await entry.pipeline.drain()
                entry.fanout = None
        return result

    def get_state(self, chat_id: str) -> str | None:
        """Return chat state or None if not found."""

        live = self._live.get(chat_id)
        if live is not None:
            return live.session.state
        persisted = self._persisted_only.get(chat_id)
        if persisted is not None:
            return persisted.state
        return self._load_state_from_disk(chat_id)

    def get_stream_source(self, chat_id: str) -> ChatStreamSource | None:
        """Return event log + optional fanout for replay."""

        live = self._live.get(chat_id)
        if live is not None:
            return ChatStreamSource(live.event_log, live.fanout)
        persisted = self._persisted_only.get(chat_id)
        if persisted is not None:
            return ChatStreamSource(persisted.event_log, None)
        record = self._load_record_from_disk(chat_id)
        if record is None:
            return None
        return ChatStreamSource(record.event_log, None)

    def get_pipeline(self, chat_id: str) -> ChatEventPipeline | None:
        """Return the live pipeline for a chat, if one is registered."""

        entry = self._live.get(chat_id)
        return entry.pipeline if entry is not None else None

    def active_chat_count(self) -> int:
        return sum(1 for entry in self._live.values() if entry.session.state != "closed")

    def register_live(self, chat_id: str, entry: LiveChatEntry) -> None:
        self._ensure_running()
        self._persisted_only.pop(chat_id, None)
        self._live[chat_id] = entry

    def register_persisted_only(self, chat_id: str, record: PersistedChatRecord) -> None:
        self._ensure_running()
        if chat_id not in self._live:
            self._persisted_only[chat_id] = record

    def live_event_index(self, chat_id: str) -> ChatEventIndex | None:
        live = self._live.get(chat_id)
        return live.event_index if live is not None else None

    def persisted_event_index(self, chat_id: str) -> ChatEventIndex | None:
        persisted = self._persisted_only.get(chat_id)
        return persisted.event_index if persisted is not None else None

    def _load_state_from_disk(self, chat_id: str) -> str | None:
        record = self._load_record_from_disk(chat_id)
        if record is None:
            return None
        if record.closed:
            self.register_persisted_only(
                chat_id,
                PersistedChatRecord(
                    event_log=record.event_log,
                    event_index=record.event_index,
                    state="closed",
                ),
            )
            return "closed"
        return "idle"

    def _load_record_from_disk(self, chat_id: str) -> _DiskChatRecord | None:
        path = self.paths.chat_history_path(chat_id)
        if not path.exists():
            return None
        event_log = ChatEventLog(path)
        event_index = self._load_event_index(chat_id)
        events = list(event_log.read_all())
        if not events:
            return None
        return _DiskChatRecord(
            event_log=event_log,
            event_index=event_index,
            closed=any(event.type == CHAT_EXITED for event in events),
        )

    def _load_event_index(self, chat_id: str) -> ChatEventIndex:
        event_index = self.live_event_index(chat_id)
        if event_index is not None:
            return event_index
        event_index = self.persisted_event_index(chat_id)
        if event_index is not None:
            return event_index
        return ChatEventIndex(self.paths.chats_dir / chat_id / "index.sqlite3")

    def _ensure_running(self) -> None:
        if self._stopped:
            raise RuntimeError("chat runtime is stopped")


@dataclass(frozen=True)
class _DiskChatRecord:
    event_log: ChatEventLog
    event_index: ChatEventIndex
    closed: bool


def build_live_entry(
    *,
    chat_id: str,
    event_log: ChatEventLog,
    event_index: ChatEventIndex,
    backend_acquisition: BackendAcquisition,
    project_root: Path,
    checkpoint_lock: asyncio.Lock,
    active_chat_counter: Callable[[], int],
) -> LiveChatEntry:
    """Build the service bundle for one live chat registry entry."""

    session = ChatSessionService(chat_id, backend_acquisition)
    fanout = WebSocketFanOut()
    pipeline = ChatEventPipeline(
        chat_id,
        event_log,
        session,
        event_index=event_index,
        fanout=fanout,
    )
    checkpoint = CheckpointService(
        project_root,
        pipeline,
        chat_registry=active_chat_counter,
        checkpoint_lock=checkpoint_lock,
    )
    pipeline.set_turn_completed_callback(
        lambda event, service=checkpoint: _checkpoint_turn(service, event)
    )
    return LiveChatEntry(
        session=session,
        event_log=event_log,
        event_index=event_index,
        fanout=fanout,
        pipeline=pipeline,
        checkpoint=checkpoint,
    )


async def _checkpoint_turn(service: CheckpointService, event: ChatEvent) -> None:
    turn_id = event.turn_id
    if turn_id is None:
        raw_turn_id = event.payload.get("turn_id")
        turn_id = raw_turn_id if isinstance(raw_turn_id, str) else None
    if turn_id:
        await service.create_checkpoint(turn_id)


__all__ = [
    "ChatRuntime",
    "ChatRuntimeView",
    "ChatStreamSource",
    "LiveChatEntry",
    "PersistedChatRecord",
    "PipelineLookup",
    "build_live_entry",
]

"""Observer bridge from SpawnManager harness events to ChatEvents."""

from __future__ import annotations

from meridian.lib.chat.event_pipeline import ChatEventPipeline
from meridian.lib.chat.normalization.base import EventNormalizer
from meridian.lib.chat.protocol import ChatEvent
from meridian.lib.core.types import SpawnId
from meridian.lib.harness.connections.base import HarnessEvent
from meridian.lib.streaming.event_observers import EventObserver


class ChatEventObserver(EventObserver):
    """R4 observer that feeds normalized harness events into the chat pipeline."""

    def __init__(
        self,
        normalizer: EventNormalizer,
        pipeline: ChatEventPipeline,
        execution_id: str,
        execution_generation: int | None = None,
    ) -> None:
        self._normalizer = normalizer
        self._pipeline = pipeline
        self._execution_id = execution_id
        self._execution_generation = execution_generation

    async def on_event(self, spawn_id: SpawnId, event: HarnessEvent) -> None:
        _ = spawn_id
        for chat_event in self._normalizer.normalize(event):
            if chat_event.execution_id != self._execution_id:
                continue
            await self._pipeline.ingest(_with_generation(chat_event, self._execution_generation))

    async def on_complete(self, spawn_id: SpawnId) -> None:
        _ = spawn_id
        self._normalizer.reset()
        await self._pipeline.on_execution_complete(self._execution_generation)


def _with_generation(event: ChatEvent, generation: int | None) -> ChatEvent:
    if generation is None or "execution_generation" in event.payload:
        return event
    return ChatEvent(
        type=event.type,
        seq=event.seq,
        chat_id=event.chat_id,
        execution_id=event.execution_id,
        timestamp=event.timestamp,
        turn_id=event.turn_id,
        item_id=event.item_id,
        request_id=event.request_id,
        payload={**event.payload, "execution_generation": generation},
        harness_id=event.harness_id,
    )


__all__ = ["ChatEventObserver", "EventNormalizer"]

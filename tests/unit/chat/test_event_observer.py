import pytest

from meridian.lib.chat.event_observer import ChatEventObserver
from meridian.lib.chat.protocol import ChatEvent, utc_now_iso
from meridian.lib.core.types import SpawnId
from meridian.lib.harness.connections.base import HarnessEvent


class FakeNormalizer:
    def __init__(self, output_events):
        self.output_events = output_events
        self.seen = []
        self.reset_calls = 0

    def normalize(self, event):
        self.seen.append(event)
        return list(self.output_events)

    def reset(self):
        self.reset_calls += 1


class FakePipeline:
    def __init__(self):
        self.events = []
        self.completed = []

    async def ingest(self, event):
        self.events.append(event)

    async def on_execution_complete(self, execution_generation=None):
        self.completed.append(execution_generation)


def chat_event(execution_id: str, *, payload=None):
    return ChatEvent(
        type="content.delta",
        seq=0,
        chat_id="c1",
        execution_id=execution_id,
        timestamp=utc_now_iso(),
        payload={} if payload is None else payload,
    )


@pytest.mark.asyncio
async def test_observer_fences_events_by_execution_id():
    pipeline = FakePipeline()
    normalizer = FakeNormalizer(
        [
            chat_event("current-exec"),
            chat_event("stale-exec"),
        ]
    )
    observer = ChatEventObserver(normalizer, pipeline, execution_id="current-exec")

    await observer.on_event(
        SpawnId("s1"),
        HarnessEvent(event_type="turn/completed", payload={}, harness_id="codex"),
    )

    assert [event.execution_id for event in pipeline.events] == ["current-exec"]


@pytest.mark.asyncio
async def test_observer_injects_execution_generation_without_overwriting_existing_value():
    pipeline = FakePipeline()
    normalizer = FakeNormalizer(
        [
            chat_event("current-exec"),
            chat_event("current-exec", payload={"execution_generation": 99}),
        ]
    )
    observer = ChatEventObserver(
        normalizer,
        pipeline,
        execution_id="current-exec",
        execution_generation=7,
    )

    await observer.on_event(
        SpawnId("s1"),
        HarnessEvent(event_type="content_block_delta", payload={}, harness_id="claude"),
    )

    assert pipeline.events[0].payload["execution_generation"] == 7
    assert pipeline.events[1].payload["execution_generation"] == 99


@pytest.mark.asyncio
async def test_observer_completion_resets_normalizer_and_notifies_pipeline():
    pipeline = FakePipeline()
    normalizer = FakeNormalizer([])
    observer = ChatEventObserver(
        normalizer,
        pipeline,
        execution_id="current-exec",
        execution_generation=3,
    )

    await observer.on_complete(SpawnId("s1"))

    assert normalizer.reset_calls == 1
    assert pipeline.completed == [3]

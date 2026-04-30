import pytest

from meridian.lib.chat.session_service import (
    ChatClosedError,
    ChatSessionService,
    ConcurrentPromptError,
)
from meridian.lib.core.types import SpawnId


class FakeHandle:
    def __init__(self, healthy=True):
        self.spawn_id = SpawnId("s1")
        self._healthy = healthy
        self.messages = []
        self.cancelled = False
        self.stopped = False

    def health(self):
        return self._healthy

    async def send_message(self, text):
        self.messages.append(text)

    async def send_cancel(self):
        self.cancelled = True

    async def stop(self):
        self.stopped = True


class FakeAcquisition:
    def __init__(self):
        self.handles = []
        self.prompts = []

    async def acquire(self, chat_id, initial_prompt, *, execution_generation=0):
        self.prompts.append((chat_id, initial_prompt, execution_generation))
        handle = FakeHandle()
        self.handles.append(handle)
        return handle


@pytest.mark.asyncio
async def test_first_prompt_acquires_backend_and_sets_active():
    acquisition = FakeAcquisition()
    session = ChatSessionService("c1", acquisition)

    await session.prompt("hello")

    assert session.state == "active"
    assert acquisition.prompts == [("c1", "hello", 1)]
    assert session.execution_generation == 1


@pytest.mark.asyncio
async def test_active_prompt_rejected_until_turn_completed():
    session = ChatSessionService("c1", FakeAcquisition())
    await session.prompt("hello")

    with pytest.raises(ConcurrentPromptError):
        await session.prompt("again")

    session.on_turn_completed()
    await session.prompt("again")
    assert session.state == "active"


@pytest.mark.asyncio
async def test_cancel_drains_and_completion_returns_idle():
    session = ChatSessionService("c1", FakeAcquisition())
    await session.prompt("hello")
    handle = session.current_execution

    await session.cancel()

    assert session.state == "draining"
    assert handle.cancelled
    session.on_turn_completed()
    assert session.state == "idle"


@pytest.mark.asyncio
async def test_idle_cancel_is_success_without_side_effect():
    session = ChatSessionService("c1", FakeAcquisition())

    await session.cancel()

    assert session.state == "idle"


@pytest.mark.asyncio
async def test_dead_backend_reacquired_on_prompt():
    acquisition = FakeAcquisition()
    session = ChatSessionService("c1", acquisition)
    await session.prompt("one")
    first = session.current_execution
    first._healthy = False
    session.on_turn_completed()

    await session.prompt("two")

    assert len(acquisition.handles) == 2
    assert session.execution_generation == 2


@pytest.mark.asyncio
async def test_close_blocks_prompts():
    session = ChatSessionService("c1", FakeAcquisition())
    await session.close()

    with pytest.raises(ChatClosedError):
        await session.prompt("no")

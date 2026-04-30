import pytest

from meridian.lib.chat.session_service import ChatSessionService
from meridian.lib.core.types import SpawnId


class Handle:
    spawn_id = SpawnId("s1")
    def health(self): return True
    async def send_message(self, text): pass
    async def send_cancel(self): pass
    async def stop(self): pass

class Acquisition:
    async def acquire(self, chat_id, initial_prompt, *, execution_generation=0):
        _ = (chat_id, initial_prompt, execution_generation)
        return Handle()

@pytest.mark.asyncio
async def test_idle_active_draining_idle_closed_lifecycle():
    session = ChatSessionService("c1", Acquisition())
    assert session.state == "idle"
    await session.prompt("hi")
    assert session.state == "active"
    await session.cancel()
    assert session.state == "draining"
    session.on_turn_completed()
    assert session.state == "idle"
    await session.close()
    assert session.state == "closed"

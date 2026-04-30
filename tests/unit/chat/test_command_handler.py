import pytest

from meridian.lib.chat.command_handler import ChatCommandHandler
from meridian.lib.chat.commands import ChatCommand
from meridian.lib.chat.session_service import ChatSessionService
from meridian.lib.core.types import SpawnId


class FakeHandle:
    spawn_id = SpawnId("s1")
    def __init__(self):
        self.requests = []
        self.inputs = []
    def health(self): return True
    async def send_message(self, text): pass
    async def send_cancel(self): pass
    async def stop(self): pass
    async def respond_request(self, request_id, decision, payload=None):
        self.requests.append((request_id, decision, payload))
    async def respond_user_input(self, request_id, answers):
        self.inputs.append((request_id, answers))

class FakeAcquisition:
    def __init__(self): self.handle = FakeHandle()
    async def acquire(self, chat_id, initial_prompt, *, execution_generation=0):
        _ = (chat_id, initial_prompt, execution_generation)
        return self.handle


def command(kind, payload=None):
    return ChatCommand(kind, "cmd1", "c1", "now", payload or {})

@pytest.mark.asyncio
async def test_unknown_chat_rejected():
    result = await ChatCommandHandler({}).dispatch(command("prompt", {"text": "hi"}))
    assert result.status == "rejected"
    assert result.error == "chat_not_found"

@pytest.mark.asyncio
async def test_prompt_and_concurrent_prompt_dispatch():
    session = ChatSessionService("c1", FakeAcquisition())
    handler = ChatCommandHandler({"c1": session})

    assert (await handler.dispatch(command("prompt", {"text": "hi"}))).status == "accepted"
    result = await handler.dispatch(command("prompt", {"text": "again"}))

    assert result.status == "rejected"
    assert result.error == "concurrent_prompt"

@pytest.mark.asyncio
async def test_unsupported_deferred_commands_rejected_centrally():
    session = ChatSessionService("c1", FakeAcquisition())
    handler = ChatCommandHandler({"c1": session})

    result = await handler.dispatch(command("swap_model", {"model": "x"}))

    assert result.status == "rejected"
    assert result.error == "not_supported_by_current_harness"

@pytest.mark.asyncio
async def test_approve_requires_active_execution():
    session = ChatSessionService("c1", FakeAcquisition())
    handler = ChatCommandHandler({"c1": session})

    result = await handler.dispatch(command("approve", {"request_id": "r1", "decision": "accept"}))

    assert result.status == "rejected"
    assert result.error == "no_active_execution"

@pytest.mark.asyncio
async def test_approve_routes_to_backend_handle():
    acquisition = FakeAcquisition()
    session = ChatSessionService("c1", acquisition)
    await session.prompt("hi")
    handler = ChatCommandHandler({"c1": session})

    result = await handler.dispatch(
        command(
            "approve",
            {"request_id": "r1", "decision": "accept", "payload": {"x": 1}},
        )
    )

    assert result.status == "accepted"
    assert acquisition.handle.requests == [("r1", "accept", {"x": 1})]

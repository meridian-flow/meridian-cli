from pathlib import Path

from fastapi.testclient import TestClient

from meridian.lib.chat.server import app, configure
from meridian.lib.core.types import SpawnId


class Handle:
    spawn_id = SpawnId("p-hitl")

    def __init__(self):
        self.requests = []
        self.inputs = []

    def health(self):
        return True

    async def send_message(self, text):
        pass

    async def send_cancel(self):
        pass

    async def stop(self):
        pass

    async def respond_request(self, request_id, decision, payload=None):
        self.requests.append((request_id, decision, payload))

    async def respond_user_input(self, request_id, answers):
        self.inputs.append((request_id, answers))


class Acquisition:
    def __init__(self):
        self.handle = Handle()

    async def acquire(self, chat_id, initial_prompt, *, execution_generation=0):
        _ = (chat_id, initial_prompt, execution_generation)
        return self.handle


def test_approve_and_input_routes_emit_resolution_events(tmp_path: Path) -> None:
    acquisition = Acquisition()
    configure(runtime_root=tmp_path, backend_acquisition=acquisition, project_root=tmp_path)
    with TestClient(app) as client:
        chat_id = client.post("/chat", json={}).json()["chat_id"]
        assert (
            client.post(f"/chat/{chat_id}/msg", json={"text": "hi"}).json()["status"] == "accepted"
        )
        assert (
            client.post(
                f"/chat/{chat_id}/approve",
                json={"request_id": "r1", "decision": "accept", "payload": {"x": 1}},
            ).json()["status"]
            == "accepted"
        )
        assert (
            client.post(
                f"/chat/{chat_id}/input", json={"request_id": "i1", "answers": {"name": "Ada"}}
            ).json()["status"]
            == "accepted"
        )
        with client.websocket_connect(f"/ws/chat/{chat_id}") as ws:
            events = [ws.receive_json(), ws.receive_json(), ws.receive_json()]

    assert acquisition.handle.requests == [("r1", "accept", {"x": 1})]
    assert acquisition.handle.inputs == [("i1", {"name": "Ada"})]
    assert [event["type"] for event in events] == [
        "chat.started",
        "request.resolved",
        "user_input.resolved",
    ]

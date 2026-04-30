from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from meridian.lib.chat.server import app, configure
from meridian.lib.core.types import SpawnId


class Handle:
    spawn_id = SpawnId("p-test")
    def health(self) -> bool: return True
    async def send_message(self, text: str) -> None: pass
    async def send_cancel(self) -> None: pass
    async def stop(self) -> None: pass


class Acquisition:
    async def acquire(self, chat_id: str, initial_prompt: str) -> Handle:
        _ = (chat_id, initial_prompt)
        return Handle()


def test_websocket_command_ack_uses_command_type_discriminator(tmp_path: Path) -> None:
    configure(runtime_root=tmp_path, backend_acquisition=Acquisition())
    with TestClient(app) as client:
        chat_id = client.post("/chat", json={}).json()["chat_id"]
        with client.websocket_connect(f"/ws/chat/{chat_id}") as ws:
            assert ws.receive_json()["type"] == "chat.started"
            ws.send_json({
                "command_type": "prompt",
                "command_id": "cmd-1",
                "chat_id": chat_id,
                "timestamp": "2026-04-29T00:00:00Z",
                "payload": {"text": "hi"},
            })
            assert ws.receive_json() == {"ack": "cmd-1", "status": "accepted"}
            ws.send_json({
                "command_type": "prompt",
                "command_id": "cmd-2",
                "chat_id": chat_id,
                "timestamp": "2026-04-29T00:00:00Z",
                "payload": {"text": "again"},
            })
            assert ws.receive_json() == {
                "ack": "cmd-2",
                "status": "rejected",
                "error": "concurrent_prompt",
            }

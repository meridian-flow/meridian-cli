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
    async def acquire(
        self,
        chat_id: str,
        initial_prompt: str,
        *,
        execution_generation: int = 0,
    ) -> Handle:
        _ = (chat_id, initial_prompt, execution_generation)
        return Handle()


def test_replay_without_last_seq_and_with_last_seq(tmp_path: Path) -> None:
    configure(runtime_root=tmp_path, backend_acquisition=Acquisition())
    with TestClient(app) as client:
        chat_id = client.post("/chat", json={}).json()["chat_id"]
        client.post(f"/chat/{chat_id}/close")

        with client.websocket_connect(f"/ws/chat/{chat_id}") as ws:
            first = ws.receive_json()
            second = ws.receive_json()
        assert first["type"] == "chat.started"
        assert second["type"] == "chat.exited"

        with client.websocket_connect(f"/ws/chat/{chat_id}?last_seq={first['seq']}") as ws:
            assert ws.receive_json()["type"] == "chat.exited"

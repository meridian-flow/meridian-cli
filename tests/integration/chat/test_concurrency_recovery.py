from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import meridian.lib.chat.server as server
from meridian.lib.chat.protocol import ChatEvent, utc_now_iso
from meridian.lib.chat.server import app, configure
from meridian.lib.core.types import SpawnId


class Handle:
    spawn_id = SpawnId("p-recovery")

    def health(self) -> bool:
        return True

    async def send_message(self, text: str) -> None:
        pass

    async def send_cancel(self) -> None:
        pass

    async def stop(self) -> None:
        pass


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



def test_restart_recovery_restores_non_closed_chat_to_idle_and_emits_runtime_error(
    tmp_path: Path,
) -> None:
    configure(runtime_root=tmp_path, backend_acquisition=Acquisition())
    with TestClient(app) as client:
        chat_id = client.post("/chat", json={}).json()["chat_id"]
        assert (
            client.post(f"/chat/{chat_id}/msg", json={"text": "hi"}).json()["status"]
            == "accepted"
        )
        pipeline = server._runtime.live_entries[chat_id].pipeline
        client.portal.call(
            pipeline.ingest,
            ChatEvent(
                type="turn.started",
                seq=0,
                chat_id=chat_id,
                execution_id="p-recovery",
                timestamp=utc_now_iso(),
            ),
        )
        client.portal.call(pipeline.drain)

    configure(runtime_root=tmp_path, backend_acquisition=Acquisition())
    with TestClient(app) as client:
        assert client.get(f"/chat/{chat_id}/state").json() == {"chat_id": chat_id, "state": "idle"}
        with client.websocket_connect(f"/ws/chat/{chat_id}") as ws:
            events = [ws.receive_json(), ws.receive_json(), ws.receive_json()]

    assert [event["type"] for event in events] == [
        "chat.started",
        "turn.started",
        "runtime.error",
    ]
    assert events[-1]["payload"]["reason"] == "backend_lost_after_restart"

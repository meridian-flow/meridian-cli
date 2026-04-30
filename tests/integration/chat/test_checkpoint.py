from pathlib import Path

from fastapi.testclient import TestClient

import meridian.lib.chat.server as server
from meridian.lib.chat.server import app, configure
from meridian.lib.core.types import SpawnId


class Handle:
    spawn_id = SpawnId("p-checkpoint")

    def health(self):
        return True

    async def send_message(self, text):
        pass

    async def send_cancel(self):
        pass

    async def stop(self):
        pass


class Acquisition:
    async def acquire(self, chat_id, initial_prompt, *, execution_generation=0):
        _ = (chat_id, initial_prompt, execution_generation)
        return Handle()


def run(cmd: list[str], cwd: Path) -> None:
    import subprocess

    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)


def test_turn_completed_creates_checkpoint_and_revert_restores_file(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    run(["git", "init"], project)
    run(["git", "config", "user.email", "test@example.com"], project)
    run(["git", "config", "user.name", "Test User"], project)
    tracked = project / "tracked.txt"
    tracked.write_text("base\n", encoding="utf-8")
    run(["git", "add", "tracked.txt"], project)
    run(["git", "commit", "-m", "base"], project)

    runtime = tmp_path / "runtime"
    configure(runtime_root=runtime, backend_acquisition=Acquisition(), project_root=project)
    with TestClient(app) as client:
        chat_id = client.post("/chat", json={}).json()["chat_id"]
        tracked.write_text("changed\n", encoding="utf-8")
        import anyio

        commit_sha = anyio.run(server._state.checkpoints[chat_id].create_checkpoint, "t1")
        tracked.write_text("after\n", encoding="utf-8")
        assert (
            client.post(f"/chat/{chat_id}/revert", json={"commit_sha": commit_sha}).json()[
                "status"
            ]
            == "accepted"
        )

    assert tracked.read_text(encoding="utf-8") == "changed\n"

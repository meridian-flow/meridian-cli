from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from meridian.lib.core.lifecycle import generate_lifecycle_event_id
from meridian.lib.ops.work_lifecycle import (
    WorkDoneInput,
    WorkStartInput,
    work_done_sync,
    work_start_sync,
)

if TYPE_CHECKING:
    import pytest


def _python_command(script_path: Path, *args: str) -> str:
    return subprocess.list2cmdline([sys.executable, str(script_path), *args])


def _write_hook_recorder(path: Path) -> None:
    path.write_text(
        "import json\n"
        "import sys\n"
        "from pathlib import Path\n"
        "payload = json.loads(sys.stdin.read())\n"
        "target = Path(sys.argv[1])\n"
        "target.parent.mkdir(parents=True, exist_ok=True)\n"
        "with target.open('a', encoding='utf-8') as handle:\n"
        "    handle.write(json.dumps(payload) + '\\n')\n",
        encoding="utf-8",
    )


def test_work_lifecycle_dispatches_started_and_done_hooks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_root = tmp_path / "repo"
    project_root.mkdir()
    (project_root / ".git").mkdir()
    state_root = project_root / ".meridian"

    user_config = tmp_path / "user-config.toml"
    user_config.write_text("", encoding="utf-8")
    monkeypatch.setenv("MERIDIAN_CONFIG", user_config.as_posix())
    monkeypatch.setenv("MERIDIAN_RUNTIME_DIR", state_root.as_posix())
    monkeypatch.setenv("MERIDIAN_HOOKS_ENABLED", "true")

    marker = tmp_path / "work-hook-events.jsonl"
    recorder = tmp_path / "record_hook.py"
    _write_hook_recorder(recorder)
    command = _python_command(recorder, marker.as_posix())

    (project_root / "meridian.toml").write_text(
        f"[[hooks]]\n"
        f"name = 'record-work-started'\n"
        f"event = 'work.started'\n"
        f"command = '{command}'\n\n"
        f"[[hooks]]\n"
        f"name = 'record-work-done'\n"
        f"event = 'work.done'\n"
        f"command = '{command}'\n",
        encoding="utf-8",
    )

    started = work_start_sync(
        WorkStartInput(
            label="phase-four-hooks",
            description="hook dispatch check",
            chat_id="chat-1",
            project_root=project_root.as_posix(),
        )
    )
    work_done_sync(
        WorkDoneInput(
            work_id=started.name,
            project_root=project_root.as_posix(),
        )
    )

    payloads = [json.loads(line) for line in marker.read_text(encoding="utf-8").splitlines()]
    assert len(payloads) == 2
    by_event = {payload["event_name"]: payload for payload in payloads}

    started_payload = by_event["work.started"]
    assert started_payload["event_id"] == str(
        generate_lifecycle_event_id(started.name, "work.started", 0)
    )
    assert started_payload["project_root"] == project_root.resolve().as_posix()
    assert started_payload["runtime_root"] == state_root.resolve().as_posix()
    assert started_payload["spawn"] is None
    assert started_payload["work"]["id"] == started.name
    assert Path(started_payload["work"]["dir"]).name == started.name

    done_payload = by_event["work.done"]
    assert done_payload["event_id"] == str(
        generate_lifecycle_event_id(started.name, "work.done", 0)
    )
    assert done_payload["spawn"] is None
    assert done_payload["work"]["id"] == started.name
    assert Path(done_payload["work"]["dir"]).name == started.name

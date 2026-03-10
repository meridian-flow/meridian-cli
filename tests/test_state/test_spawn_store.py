
import json

from meridian.lib.state.spawn_store import get_spawn, list_spawns, start_spawn


def _state_root(tmp_path):
    state_dir = tmp_path / ".meridian"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def test_list_runs_skips_truncated_trailing_json(tmp_path):
    state_root = _state_root(tmp_path)
    spawns_jsonl = state_root / "spawns.jsonl"
    with spawns_jsonl.open("w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "start",
                    "id": "r1",
                    "chat_id": "c1",
                    "model": "gpt-5.3-codex",
                    "agent": "coder",
                    "harness": "codex",
                    "status": "running",
                    "started_at": "2026-03-01T00:00:00Z",
                    "prompt": "hello",
                }
            )
            + "\n"
        )
        handle.write('{"v":1,"event":"finalize","id":"r1","status":"succeeded"')

    spawns = list_spawns(state_root)
    assert len(spawns) == 1
    assert spawns[0].id == "r1"
    assert spawns[0].status == "running"


def test_spawn_record_preserves_desc_and_work_id(tmp_path):
    state_root = _state_root(tmp_path)

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
        desc="investigate bug",
        work_id="work-7",
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.desc == "investigate bug"
    assert row.work_id == "work-7"

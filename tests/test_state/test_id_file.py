
import json

from meridian.lib.state.spawn_store import next_spawn_id, next_chat_id, next_space_id


def test_next_space_id_starts_at_s1(tmp_path):
    assert next_space_id(tmp_path) == "s1"


def test_next_space_id_uses_max_numeric_suffix(tmp_path):
    spaces_dir = tmp_path / ".meridian" / ".spaces"
    spaces_dir.mkdir(parents=True, exist_ok=True)
    (spaces_dir / "s1").mkdir()
    (spaces_dir / "s9").mkdir()
    (spaces_dir / "s2").mkdir()
    (spaces_dir / "x5").mkdir()
    (spaces_dir / "sabc").mkdir()

    assert next_space_id(tmp_path) == "s10"


def test_next_run_id_counts_start_events_and_skips_truncated_trailing_line(tmp_path):
    space_dir = tmp_path / ".meridian" / ".spaces" / "s1"
    space_dir.mkdir(parents=True, exist_ok=True)
    spawns_jsonl = space_dir / "spawns.jsonl"
    with spawns_jsonl.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"v": 1, "event": "start", "id": "r1"}) + "\n")
        handle.write(json.dumps({"v": 1, "event": "finalize", "id": "r1"}) + "\n")
        handle.write(json.dumps({"v": 1, "event": "start", "id": "r2"}) + "\n")
        handle.write('{"v":1,"event":"start","id":"r3"')

    assert next_spawn_id(space_dir) == "p3"


def test_next_chat_id_counts_start_events(tmp_path):
    space_dir = tmp_path / ".meridian" / ".spaces" / "s2"
    space_dir.mkdir(parents=True, exist_ok=True)
    sessions_jsonl = space_dir / "sessions.jsonl"
    with sessions_jsonl.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps({"v": 1, "event": "start", "chat_id": "c1"}) + "\n")
        handle.write(json.dumps({"v": 1, "event": "stop", "chat_id": "c1"}) + "\n")
        handle.write(json.dumps({"v": 1, "event": "start", "chat_id": "c2"}) + "\n")

    assert next_chat_id(space_dir) == "c3"

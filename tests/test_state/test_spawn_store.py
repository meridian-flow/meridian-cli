
import json

from meridian.lib.state.spawn_store import finalize_spawn, get_spawn, list_spawns, spawn_stats, start_spawn

def _space_dir(tmp_path):
    space_dir = tmp_path / ".meridian" / ".spaces" / "s1"
    space_dir.mkdir(parents=True, exist_ok=True)
    return space_dir

def test_start_and_finalize_run_round_trip(tmp_path):
    space_dir = _space_dir(tmp_path)

    spawn_id = start_spawn(
        space_dir,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt="hello",
        harness_session_id="hs-1",
    )
    finalize_spawn(
        space_dir,
        spawn_id,
        "succeeded",
        0,
        duration_secs=12.5,
        total_cost_usd=0.05,
        input_tokens=42,
        output_tokens=17,
    )

    loaded = get_spawn(space_dir, spawn_id)
    assert loaded is not None
    assert loaded.id == "p1"
    assert loaded.kind == "child"
    assert loaded.status == "succeeded"
    assert loaded.model == "gpt-5.3-codex"
    assert loaded.chat_id == "c1"
    assert loaded.exit_code == 0
    assert loaded.duration_secs == 12.5
    assert loaded.total_cost_usd == 0.05
    assert loaded.input_tokens == 42
    assert loaded.output_tokens == 17

def test_start_run_writes_schema_version(tmp_path):
    space_dir = _space_dir(tmp_path)
    start_spawn(
        space_dir,
        chat_id="c1",
        model="claude-sonnet-4-6",
        agent="coder",
        harness="claude",
        prompt="test",
    )

    first = (space_dir / "spawns.jsonl").read_text(encoding="utf-8").splitlines()[0]
    payload = json.loads(first)
    assert payload["v"] == 1
    assert payload["event"] == "start"
    assert payload["id"] == "p1"

def test_list_runs_skips_truncated_trailing_json(tmp_path):
    space_dir = _space_dir(tmp_path)
    spawns_jsonl = space_dir / "spawns.jsonl"
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

    spawns = list_spawns(space_dir)
    assert len(spawns) == 1
    assert spawns[0].id == "r1"
    assert spawns[0].status == "running"

def test_run_stats_aggregates_model_status_cost_duration_and_tokens(tmp_path):
    space_dir = _space_dir(tmp_path)

    r1 = start_spawn(
        space_dir,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt="a",
    )
    r2 = start_spawn(
        space_dir,
        chat_id="c2",
        model="claude-sonnet-4-6",
        agent="reviewer",
        harness="claude",
        prompt="b",
    )
    finalize_spawn(
        space_dir,
        r1,
        "succeeded",
        0,
        duration_secs=4.0,
        total_cost_usd=0.1,
        input_tokens=100,
        output_tokens=50,
    )
    finalize_spawn(
        space_dir,
        r2,
        "failed",
        1,
        duration_secs=6.0,
        total_cost_usd=0.2,
        input_tokens=20,
        output_tokens=10,
    )

    stats = spawn_stats(space_dir)
    assert stats["total_runs"] == 2
    assert stats["by_status"] == {"failed": 1, "succeeded": 1}
    assert stats["by_model"] == {"claude-sonnet-4-6": 1, "gpt-5.3-codex": 1}
    assert stats["total_duration_secs"] == 10.0
    assert stats["total_cost_usd"] == 0.30000000000000004
    assert stats["total_input_tokens"] == 120
    assert stats["total_output_tokens"] == 60

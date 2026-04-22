# State Integrity

Run these checks after any smoke test that creates `.meridian/` state. The goal is to catch malformed JSONL, missing guard files, or stale lock behavior before it becomes a debugging session.

## Setup

```bash
export REPO_ROOT=/abs/path/to/meridian-channel
export SMOKE_REPO="$(mktemp -d /tmp/meridian-state.XXXXXX)"
git -C "$SMOKE_REPO" init --quiet
for var in $(env | awk -F= '/^MERIDIAN_/ {print $1}'); do unset "$var"; done
export MERIDIAN_PROJECT_DIR="$SMOKE_REPO"
export MERIDIAN_RUNTIME_DIR="$SMOKE_REPO/.meridian"
cd "$REPO_ROOT"
uv run meridian --help >/dev/null && echo "PASS: base state fixture created" || echo "FAIL: state fixture setup failed"
```

### STATE-1. Core `.meridian/` structure exists [CRITICAL]

```bash
test -d "$MERIDIAN_RUNTIME_DIR/fs" && \
test -d "$MERIDIAN_RUNTIME_DIR/spawns" && \
test -f "$MERIDIAN_RUNTIME_DIR/.gitignore" && \
echo "PASS: core state directories exist" || echo "FAIL: core state directories are incomplete"
```

### STATE-2. `spawns.jsonl` contains valid JSON objects [IMPORTANT]

```bash
uv run python - <<'PY'
import json, os, sys
path = os.path.join(os.environ["MERIDIAN_RUNTIME_DIR"], "spawns.jsonl")
if not os.path.exists(path):
    print("PASS: no spawns.jsonl yet; run lifecycle smoke to populate it")
else:
    with open(path) as fh:
        lines = [line.strip() for line in fh if line.strip()]
    assert lines
    for line in lines:
        doc = json.loads(line)
        assert isinstance(doc, dict)
        assert "spawn_id" in doc or "id" in doc
    print("PASS: spawns.jsonl is well-formed")
PY
```

### STATE-3. `sessions.jsonl` is valid when present [IMPORTANT]

```bash
uv run python - <<'PY'
import json, os
path = os.path.join(os.environ["MERIDIAN_RUNTIME_DIR"], "sessions.jsonl")
if not os.path.exists(path):
    print("PASS: sessions.jsonl has not been created yet")
else:
    with open(path) as fh:
        for line in fh:
            if line.strip():
                assert isinstance(json.loads(line), dict)
    print("PASS: sessions.jsonl is well-formed")
PY
```

### STATE-4. Lock files are not left unusable [IMPORTANT]

```bash
uv run python - <<'PY'
import fcntl, glob, os
root = os.environ["MERIDIAN_RUNTIME_DIR"]
locks = glob.glob(os.path.join(root, "*.lock"))
if not locks:
    print("PASS: no lock files are present")
else:
    for path in locks:
        with open(path, "a+b") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    print("PASS: lock files are acquirable")
PY
```

### STATE-5. No stale flock sidecars remain after setup [NICE-TO-HAVE]

```bash
if find "$MERIDIAN_RUNTIME_DIR" -name '*.flock' -print | grep -q .; then
  echo "FAIL: stale .flock files remain"
else
  echo "PASS: no stale .flock sidecars remain"
fi
```

### STATE-6. Dead runner + stale heartbeat (>120s) stamps `orphan_run` [CRITICAL]

```bash
uv run python - <<'PY'
import json, os, pathlib, subprocess, time

root = pathlib.Path(os.environ["MERIDIAN_RUNTIME_DIR"])
spawns_jsonl = root / "spawns.jsonl"
spawn_id = "p-orphan-heartbeat-smoke"

start_event = {
    "v": 1,
    "event": "start",
    "id": spawn_id,
    "chat_id": "c-state",
    "model": "gpt-5.4",
    "agent": "smoke",
    "harness": "codex",
    "kind": "child",
    "prompt": "state integrity smoke",
    "status": "running",
    "runner_pid": 999999,
    "started_at": "2000-01-01T00:00:00Z",
}

spawns_jsonl.parent.mkdir(parents=True, exist_ok=True)
with spawns_jsonl.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(start_event) + "\n")

spawn_dir = root / "spawns" / spawn_id
spawn_dir.mkdir(parents=True, exist_ok=True)
heartbeat = spawn_dir / "heartbeat"
heartbeat.touch(exist_ok=True)
stale_epoch = time.time() - 180
os.utime(heartbeat, (stale_epoch, stale_epoch))

subprocess.run(
    ["uv", "run", "meridian", "spawn", "show", spawn_id],
    check=False,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

events = []
with spawns_jsonl.open(encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            events.append(json.loads(line))

orphan_stamped = any(
    event.get("event") == "finalize"
    and event.get("id") == spawn_id
    and event.get("error") == "orphan_run"
    for event in events
)
assert orphan_stamped, "expected orphan_run finalize stamp after stale heartbeat window"
print("PASS: stale heartbeat window triggered orphan_run reconciliation")
PY
```

### STATE-7. Cancel path stamps `origin=\"cancel\"` [CRITICAL]

```bash
uv run python - <<'PY'
import json, os, pathlib, subprocess, uuid
from meridian.lib.state.spawn_store import start_spawn

root = pathlib.Path(os.environ["MERIDIAN_RUNTIME_DIR"])
spawn_id = f"p-origin-cancel-{uuid.uuid4().hex[:8]}"
start_spawn(
    root,
    spawn_id=spawn_id,
    chat_id="c-state",
    model="gpt-5.4",
    agent="smoke",
    harness="codex",
    prompt="cancel origin smoke",
    status="running",
)

subprocess.run(
    ["uv", "run", "meridian", "spawn", "cancel", spawn_id],
    check=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

events = []
with (root / "spawns.jsonl").open(encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            events.append(json.loads(line))

finalize_events = [
    event for event in events
    if event.get("event") == "finalize" and event.get("id") == spawn_id
]
assert finalize_events, "expected finalize event for cancelled smoke spawn"
latest = finalize_events[-1]
assert latest.get("status") == "cancelled"
assert latest.get("origin") == "cancel"
print("PASS: cancel flow writes finalize origin=cancel")
PY
```

### STATE-8. Success path records `origin=\"runner\"` [IMPORTANT]

```bash
uv run python - <<'PY'
import json, os, pathlib

root = pathlib.Path(os.environ["MERIDIAN_RUNTIME_DIR"])
spawns_jsonl = root / "spawns.jsonl"
if not spawns_jsonl.exists():
    raise AssertionError("spawns.jsonl missing")

found = False
with spawns_jsonl.open(encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if not line:
            continue
        event = json.loads(line)
        if (
            event.get("event") == "finalize"
            and event.get("status") == "succeeded"
            and event.get("origin") == "runner"
        ):
            found = True
            break

assert found, "expected at least one successful finalize with origin=runner"
print("PASS: success finalize origin=runner observed")
PY
```

### STATE-9. Stale `finalizing` heartbeat stamps `orphan_finalization` [CRITICAL]

```bash
uv run python - <<'PY'
import json, os, pathlib, subprocess, time

root = pathlib.Path(os.environ["MERIDIAN_RUNTIME_DIR"])
spawns_jsonl = root / "spawns.jsonl"
spawn_id = "p-orphan-finalizing-stale-smoke"

start_event = {
    "v": 1,
    "event": "start",
    "id": spawn_id,
    "chat_id": "c-state",
    "model": "gpt-5.4",
    "agent": "smoke",
    "harness": "codex",
    "kind": "child",
    "prompt": "finalizing stale heartbeat smoke",
    "status": "finalizing",
    "runner_pid": 999999,
    "started_at": "2000-01-01T00:00:00Z",
}

spawns_jsonl.parent.mkdir(parents=True, exist_ok=True)
with spawns_jsonl.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(start_event) + "\n")

spawn_dir = root / "spawns" / spawn_id
spawn_dir.mkdir(parents=True, exist_ok=True)
heartbeat = spawn_dir / "heartbeat"
heartbeat.touch(exist_ok=True)
stale_epoch = time.time() - 180
os.utime(heartbeat, (stale_epoch, stale_epoch))

subprocess.run(
    ["uv", "run", "meridian", "spawn", "show", spawn_id],
    check=False,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

events = []
with spawns_jsonl.open(encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            events.append(json.loads(line))

orphan_stamped = any(
    event.get("event") == "finalize"
    and event.get("id") == spawn_id
    and event.get("error") == "orphan_finalization"
    for event in events
)
assert orphan_stamped, "expected orphan_finalization finalize stamp after stale heartbeat window"
print("PASS: stale finalizing heartbeat triggered orphan_finalization reconciliation")
PY
```

### STATE-10. Recent `finalizing` heartbeat does not stamp terminal [IMPORTANT]

```bash
uv run python - <<'PY'
import json, os, pathlib, subprocess, time

root = pathlib.Path(os.environ["MERIDIAN_RUNTIME_DIR"])
spawns_jsonl = root / "spawns.jsonl"
spawn_id = "p-orphan-finalizing-fresh-smoke"

start_event = {
    "v": 1,
    "event": "start",
    "id": spawn_id,
    "chat_id": "c-state",
    "model": "gpt-5.4",
    "agent": "smoke",
    "harness": "codex",
    "kind": "child",
    "prompt": "finalizing fresh heartbeat smoke",
    "status": "finalizing",
    "runner_pid": 999999,
    "started_at": "2000-01-01T00:00:00Z",
}

spawns_jsonl.parent.mkdir(parents=True, exist_ok=True)
with spawns_jsonl.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(start_event) + "\n")

spawn_dir = root / "spawns" / spawn_id
spawn_dir.mkdir(parents=True, exist_ok=True)
heartbeat = spawn_dir / "heartbeat"
heartbeat.touch(exist_ok=True)
fresh_epoch = time.time() - 5
os.utime(heartbeat, (fresh_epoch, fresh_epoch))

subprocess.run(
    ["uv", "run", "meridian", "spawn", "show", spawn_id],
    check=False,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)

events = []
with spawns_jsonl.open(encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            events.append(json.loads(line))

finalized = any(
    event.get("event") == "finalize"
    and event.get("id") == spawn_id
    for event in events
)
assert not finalized, "unexpected finalize stamp while heartbeat is recent"
print("PASS: recent finalizing heartbeat skipped orphan reconciliation")
PY
```

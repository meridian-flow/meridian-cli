# Spawn Lifecycle

Validate the normal background flow: create, wait, show, attach a report, and inspect stats. This file requires a working spawn harness in the current session because it exercises real state changes.

## Setup

```bash
export REPO_ROOT=/abs/path/to/meridian-channel
export SMOKE_REPO="$(mktemp -d /tmp/meridian-lifecycle.XXXXXX)"
git -C "$SMOKE_REPO" init --quiet
for var in $(env | awk -F= '/^MERIDIAN_/ {print $1}'); do unset "$var"; done
export MERIDIAN_REPO_ROOT="$SMOKE_REPO"
export MERIDIAN_STATE_ROOT="$SMOKE_REPO/.meridian"
mkdir -p "$SMOKE_REPO/.agents/agents"
cat > "$SMOKE_REPO/.agents/agents/reviewer.md" <<'EOF'
# Reviewer

You are a tiny smoke-test reviewer. Reply with one short sentence.
EOF
cd "$REPO_ROOT"
uv run meridian spawn -h >/dev/null 2>&1 && echo "PASS: lifecycle setup complete" || echo "FAIL: lifecycle setup failed"
```

### LIFE-1. Background spawn returns an id [CRITICAL]

```bash
uv run meridian --json spawn -a reviewer -p "Say hello from smoke test" > /tmp/meridian-lifecycle-create.json && \
uv run python - <<'PY'
import json
doc = json.load(open("/tmp/meridian-lifecycle-create.json"))
spawn_id = doc.get("spawn_id") or doc.get("id")
assert spawn_id
print("PASS: created spawn", spawn_id)
PY
```

### LIFE-2. Wait returns a terminal status [CRITICAL]

```bash
SPAWN_ID="$(uv run python - <<'PY'
import json
doc = json.load(open("/tmp/meridian-lifecycle-create.json"))
print(doc.get("spawn_id") or doc.get("id"))
PY
)" && \
uv run meridian spawn wait "$SPAWN_ID" > /tmp/meridian-lifecycle-wait.txt 2>&1 || true
grep -Eq 'succeeded|failed|cancelled' /tmp/meridian-lifecycle-wait.txt && echo "PASS: wait reached a terminal status" || echo "FAIL: wait did not report a terminal status"
```

### LIFE-3. Show can include report metadata [IMPORTANT]

```bash
SPAWN_ID="$(uv run python - <<'PY'
import json
doc = json.load(open("/tmp/meridian-lifecycle-create.json"))
print(doc.get("spawn_id") or doc.get("id"))
PY
)" && \
uv run meridian spawn show "$SPAWN_ID" > /tmp/meridian-lifecycle-show.txt && \
grep -q 'Status:' /tmp/meridian-lifecycle-show.txt && \
grep -q "Spawn: $SPAWN_ID" /tmp/meridian-lifecycle-show.txt && \
echo "PASS: spawn show returned lifecycle data" || echo "FAIL: spawn show output was incomplete"
```

### LIFE-4. Auto-extracted report is retrievable via `report show` [IMPORTANT]

Reports are written by the spawned agent as its final assistant message; the
finalize pipeline extracts and persists the message to `spawns/<id>/report.md`.
Verify the extraction landed and `report show` surfaces it.

```bash
SPAWN_ID="$(uv run python - <<'PY'
import json
doc = json.load(open("/tmp/meridian-lifecycle-create.json"))
print(doc.get("spawn_id") or doc.get("id"))
PY
)" && \
uv run meridian spawn report show "$SPAWN_ID" > /tmp/meridian-lifecycle-report-show.txt && \
test -s "$MERIDIAN_STATE_ROOT/spawns/$SPAWN_ID/report.md" && \
test -s /tmp/meridian-lifecycle-report-show.txt && \
echo "PASS: auto-extracted report was persisted and report show returned content" || echo "FAIL: report.md missing or report show empty"
```

### LIFE-5. Stats reflect recorded runs [IMPORTANT]

```bash
uv run meridian spawn stats > /tmp/meridian-lifecycle-stats.txt && \
grep -q 'total_runs:' /tmp/meridian-lifecycle-stats.txt && \
grep -q 'failed:' /tmp/meridian-lifecycle-stats.txt && \
echo "PASS: spawn stats returned aggregate counts" || echo "FAIL: spawn stats output was incomplete"
```

### LIFE-6. Nested read (`MERIDIAN_DEPTH>0`) does not stamp `orphan_run` [CRITICAL]

```bash
uv run python - <<'PY'
import json, os, pathlib, subprocess

root = pathlib.Path(os.environ["MERIDIAN_STATE_ROOT"])
spawns_jsonl = root / "spawns.jsonl"
spawn_id = "p-depth-gate-smoke"

start_event = {
    "v": 1,
    "event": "start",
    "id": spawn_id,
    "chat_id": "c-depth",
    "model": "gpt-5.4",
    "agent": "smoke",
    "harness": "codex",
    "kind": "child",
    "prompt": "depth gate smoke",
    "status": "running",
    "runner_pid": 999999,
    "started_at": "2000-01-01T00:00:00Z",
}
spawns_jsonl.parent.mkdir(parents=True, exist_ok=True)
with spawns_jsonl.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(start_event) + "\n")

env = dict(os.environ)
env["MERIDIAN_DEPTH"] = "1"
subprocess.run(
    ["uv", "run", "meridian", "spawn", "show", spawn_id],
    check=False,
    env=env,
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
assert not orphan_stamped, "depth>0 read unexpectedly stamped orphan_run"
print("PASS: depth>0 read path skipped orphan reconciliation")
PY
```

### LIFE-7. List filter accepts `finalizing` and returns matching rows [IMPORTANT]

```bash
uv run python - <<'PY'
import json, os, pathlib

root = pathlib.Path(os.environ["MERIDIAN_STATE_ROOT"])
spawns_jsonl = root / "spawns.jsonl"
spawn_id = "p-finalizing-filter-smoke"

start_event = {
    "v": 1,
    "event": "start",
    "id": spawn_id,
    "chat_id": "c-finalizing",
    "model": "gpt-5.4",
    "agent": "smoke",
    "harness": "codex",
    "kind": "child",
    "prompt": "finalizing filter smoke",
    "status": "finalizing",
    "runner_pid": os.getpid(),
    "started_at": "2026-04-12T15:00:00Z",
}
spawns_jsonl.parent.mkdir(parents=True, exist_ok=True)
with spawns_jsonl.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(start_event) + "\n")
print("seeded", spawn_id)
PY

uv run meridian --json spawn list --status finalizing --limit 20 > /tmp/meridian-lifecycle-finalizing-list.json && \
uv run python - <<'PY'
import json

doc = json.load(open("/tmp/meridian-lifecycle-finalizing-list.json"))
spawns = doc.get("spawns", [])
assert any(row.get("spawn_id") == "p-finalizing-filter-smoke" for row in spawns), "missing seeded finalizing row"
assert all(row.get("status") == "finalizing" for row in spawns), "non-finalizing row returned"
print("PASS: --status finalizing returned only finalizing rows")
PY
```

### LIFE-8. Late status updates do not downgrade a terminal row [IMPORTANT]

```bash
uv run python - <<'PY'
import os
from pathlib import Path

from meridian.lib.state.spawn_store import (
    finalize_spawn,
    get_spawn,
    mark_finalizing,
    start_spawn,
    update_spawn,
)

state_root = Path(os.environ["MERIDIAN_STATE_ROOT"])
spawn_id = str(
    start_spawn(
        state_root,
        chat_id="c-lifecycle",
        model="gpt-5.4",
        agent="smoke",
        harness="codex",
        prompt="late update invariant smoke",
    )
)
finalize_spawn(state_root, spawn_id, status="succeeded", exit_code=0, origin="runner")
mark_finalizing(state_root, spawn_id)
update_spawn(state_root, spawn_id, desc="late update")

row = get_spawn(state_root, spawn_id)
assert row is not None
assert row.status == "succeeded", f"terminal status downgraded: {row.status}"
assert row.desc == "late update"
print("PASS: late update merged metadata without downgrading terminal status")
PY
```

# Spawn Lifecycle

Validate the normal background flow: create, wait, show, attach a report, and inspect stats. This file requires a working spawn harness in the current session because it exercises real state changes.

## Setup

```bash
export REPO_ROOT=/abs/path/to/meridian-channel
export SMOKE_REPO="$(mktemp -d /tmp/meridian-lifecycle.XXXXXX)"
export SMOKE_SOURCE="$(mktemp -d /tmp/meridian-lifecycle-source.XXXXXX)"
git -C "$SMOKE_REPO" init --quiet
for var in $(env | awk -F= '/^MERIDIAN_/ {print $1}'); do unset "$var"; done
export MERIDIAN_REPO_ROOT="$SMOKE_REPO"
export MERIDIAN_STATE_ROOT="$SMOKE_REPO/.meridian"
mkdir -p "$SMOKE_SOURCE/agents"
cat > "$SMOKE_SOURCE/agents/reviewer.md" <<'EOF'
# Reviewer

You are a tiny smoke-test reviewer. Reply with one short sentence.
EOF
cd "$REPO_ROOT"
uv run meridian install "$SMOKE_SOURCE" --name lifecycle-smoke >/tmp/meridian-lifecycle-install.txt 2>&1 && \
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
uv run meridian spawn show "$SPAWN_ID" --report > /tmp/meridian-lifecycle-show.txt && \
grep -q 'Status:' /tmp/meridian-lifecycle-show.txt && \
grep -q "Spawn: $SPAWN_ID" /tmp/meridian-lifecycle-show.txt && \
echo "PASS: spawn show returned lifecycle data" || echo "FAIL: spawn show output was incomplete"
```

### LIFE-4. Report create and show work for a finished spawn [IMPORTANT]

```bash
SPAWN_ID="$(uv run python - <<'PY'
import json
doc = json.load(open("/tmp/meridian-lifecycle-create.json"))
print(doc.get("spawn_id") or doc.get("id"))
PY
)" && \
printf '# Smoke Report\n\nLifecycle smoke test.\n' | \
uv run meridian report create --spawn "$SPAWN_ID" --stdin >/tmp/meridian-lifecycle-report.txt && \
uv run meridian report show --spawn "$SPAWN_ID" >/tmp/meridian-lifecycle-report-show.txt && \
grep -q 'report.create' /tmp/meridian-lifecycle-report.txt && \
grep -q 'Smoke Report' /tmp/meridian-lifecycle-report-show.txt && \
echo "PASS: report create and show succeeded" || echo "FAIL: report create/show output was incomplete"
```

### LIFE-5. Stats reflect recorded runs [IMPORTANT]

```bash
uv run meridian spawn stats > /tmp/meridian-lifecycle-stats.txt && \
grep -q 'total_runs:' /tmp/meridian-lifecycle-stats.txt && \
grep -q 'failed:' /tmp/meridian-lifecycle-stats.txt && \
echo "PASS: spawn stats returned aggregate counts" || echo "FAIL: spawn stats output was incomplete"
```

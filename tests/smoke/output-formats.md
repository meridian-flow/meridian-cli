# Output Formats

These checks keep the CLI output contract honest across the supported presentation modes. Use them after changing formatting, sinks, or error rendering.

## Setup

```bash
export REPO_ROOT=/abs/path/to/meridian-channel
export SMOKE_REPO="$(mktemp -d /tmp/meridian-formats.XXXXXX)"
git -C "$SMOKE_REPO" init --quiet
for var in $(env | awk -F= '/^MERIDIAN_/ {print $1}'); do unset "$var"; done
export MERIDIAN_REPO_ROOT="$SMOKE_REPO"
export MERIDIAN_STATE_ROOT="$SMOKE_REPO/.meridian"
mkdir -p "$SMOKE_REPO/.agents/agents"
cat > "$SMOKE_REPO/.agents/agents/reviewer.md" <<'EOF'
# Reviewer

Format smoke reviewer.
EOF
cd "$REPO_ROOT"
test -d "$SMOKE_REPO/.git" && echo "PASS: output-format repo ready" || echo "FAIL: output-format repo setup failed"
```

### FMT-1. `--json` returns JSON [CRITICAL]

```bash
uv run meridian --json spawn -a reviewer -p "format probe" --dry-run > /tmp/meridian-formats-json.json && \
uv run python - <<'PY'
import json
assert isinstance(json.load(open("/tmp/meridian-formats-json.json")), dict)
print("PASS: --json produced JSON")
PY
```

### FMT-2. `--format json` matches the JSON contract [CRITICAL]

```bash
uv run meridian --format json spawn -a reviewer -p "format probe" --dry-run > /tmp/meridian-formats-format-json.json && \
uv run python - <<'PY'
import json
assert isinstance(json.load(open("/tmp/meridian-formats-format-json.json")), dict)
print("PASS: --format json produced JSON")
PY
```

### FMT-3. `--format text` is human-readable [IMPORTANT]

```bash
uv run meridian --format text doctor > /tmp/meridian-formats-text.out && \
uv run python - <<'PY'
text = open("/tmp/meridian-formats-text.out").read()
assert "ok:" in text and not text.lstrip().startswith("{")
print("PASS: --format text produced text output")
PY
```

### FMT-4. Agent mode defaults to JSON output [IMPORTANT]

```bash
MERIDIAN_DEPTH=1 uv run meridian models list > /tmp/meridian-formats-agent.out && \
uv run python - <<'PY'
import json
for line in open("/tmp/meridian-formats-agent.out"):
    line = line.strip()
    if line:
        json.loads(line)
print("PASS: agent mode emitted JSON lines")
PY
```

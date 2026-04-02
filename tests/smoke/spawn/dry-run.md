# Spawn Dry-Run

These checks validate prompt assembly and argument handling without invoking a real harness. Use them when working on prompt composition, model selection, template vars, or reference-file wiring.

## Setup

```bash
export REPO_ROOT=/abs/path/to/meridian-channel
export SMOKE_REPO="$(mktemp -d /tmp/meridian-dryrun.XXXXXX)"
git -C "$SMOKE_REPO" init --quiet
for var in $(env | awk -F= '/^MERIDIAN_/ {print $1}'); do unset "$var"; done
export MERIDIAN_REPO_ROOT="$SMOKE_REPO"
export MERIDIAN_STATE_ROOT="$SMOKE_REPO/.meridian"
mkdir -p "$SMOKE_REPO/.agents/agents"
cat > "$SMOKE_REPO/.agents/agents/reviewer.md" <<'EOF'
# Reviewer

Dry-run smoke reviewer.
EOF
cd "$REPO_ROOT"
printf '# smoke ref\n' > /tmp/meridian-dryrun-ref.md
test -f /tmp/meridian-dryrun-ref.md && echo "PASS: dry-run setup complete" || echo "FAIL: dry-run setup failed"
```

### DRY-1. Basic dry-run [CRITICAL]

```bash
uv run meridian --json spawn -a reviewer -p "Write hello world" --dry-run > /tmp/meridian-dryrun-basic.json && \
uv run python - <<'PY'
import json
doc = json.load(open("/tmp/meridian-dryrun-basic.json"))
assert doc["status"] == "dry-run"
assert "Write hello world" in doc["composed_prompt"]
assert "model" in doc
print("PASS: basic dry-run succeeded")
PY
```

### DRY-2. Model override [IMPORTANT]

```bash
uv run meridian --json spawn -a reviewer -p "test model override" -m opus --dry-run > /tmp/meridian-dryrun-model.json && \
uv run python - <<'PY'
import json
doc = json.load(open("/tmp/meridian-dryrun-model.json"))
assert doc["status"] == "dry-run"
assert doc["model"]
print("PASS: model override was accepted")
PY
```

### DRY-3. Template vars [IMPORTANT]

```bash
uv run meridian --json spawn \
  -a reviewer \
  -p "Review {{FILE_PATH}} for {{CONCERN}}" \
  --prompt-var FILE_PATH=src/main.py \
  --prompt-var CONCERN=security \
  --dry-run > /tmp/meridian-dryrun-vars.json && \
uv run python - <<'PY'
import json
doc = json.load(open("/tmp/meridian-dryrun-vars.json"))
prompt = doc["composed_prompt"]
assert "src/main.py" in prompt and "security" in prompt
assert "{{FILE_PATH}}" not in prompt and "{{CONCERN}}" not in prompt
print("PASS: prompt vars were substituted")
PY
```

### DRY-4. Reference files [IMPORTANT]

```bash
uv run meridian --json spawn \
  -a reviewer \
  -p "Review this file" \
  -f /tmp/meridian-dryrun-ref.md \
  --dry-run > /tmp/meridian-dryrun-ref.json && \
uv run python - <<'PY'
import json
doc = json.load(open("/tmp/meridian-dryrun-ref.json"))
refs = doc.get("reference_files", [])
assert refs
print("PASS: reference files were attached to the dry-run payload")
PY
```

### DRY-5. Empty prompt is graceful [IMPORTANT]

```bash
if uv run meridian --json spawn -a reviewer -p "" --dry-run >/tmp/meridian-dryrun-empty.out 2>&1; then
  if grep -q "Traceback" /tmp/meridian-dryrun-empty.out; then
    echo "FAIL: empty prompt produced a traceback"
  else
    echo "PASS: empty prompt was handled cleanly"
  fi
else
  if grep -q "Traceback" /tmp/meridian-dryrun-empty.out; then
    echo "FAIL: empty prompt crashed"
  else
    echo "PASS: empty prompt failed cleanly"
  fi
fi
```

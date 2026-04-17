# Quick Sanity

Run these first. They cover the critical command surface in about five minutes and stop you from wasting time on deeper smoke tests when the CLI is already broken.

## Setup

```bash
export REPO_ROOT=/abs/path/to/meridian-channel
export SMOKE_REPO="$(mktemp -d /tmp/meridian-quick.XXXXXX)"
git -C "$SMOKE_REPO" init --quiet
for var in $(env | awk -F= '/^MERIDIAN_/ {print $1}'); do unset "$var"; done
export MERIDIAN_REPO_ROOT="$SMOKE_REPO"
export MERIDIAN_STATE_ROOT="$SMOKE_REPO/.meridian"
mkdir -p "$SMOKE_REPO/.agents/agents"
cat > "$SMOKE_REPO/.agents/agents/reviewer.md" <<'EOF'
# Reviewer

Quick sanity reviewer.
EOF
cd "$REPO_ROOT"
test -d "$SMOKE_REPO/.git" && echo "PASS: quick-sanity repo ready" || echo "FAIL: quick-sanity repo setup failed"
```

### QS-1. Help text [CRITICAL]

```bash
HELP_TEXT="$(uv run meridian --help 2>&1)" && \
printf '%s\n' "$HELP_TEXT" | grep -q 'spawn' && \
printf '%s\n' "$HELP_TEXT" | grep -q 'models' && \
printf '%s\n' "$HELP_TEXT" | grep -q 'work' && \
echo "PASS: help exposes core commands" || echo "FAIL: help is missing core commands"
```

### QS-2. Version [CRITICAL]

```bash
uv run meridian --version 2>&1 | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+' && echo "PASS: version looks valid" || echo "FAIL: version output is malformed"
```

### QS-3. First run bootstraps runtime state only and show works [CRITICAL]

```bash
uv run meridian --help >/tmp/meridian-qs-help.txt && \
uv run meridian config show >/tmp/meridian-qs-config-show.txt && \
test -d "$MERIDIAN_STATE_ROOT" && \
! test -f "$SMOKE_REPO/meridian.toml" && \
! test -f "$SMOKE_REPO/workspace.local.toml" && \
! test -d "$SMOKE_REPO/.mars" && \
! test -f "$SMOKE_REPO/mars.toml" && \
grep -q '^defaults.model:' /tmp/meridian-qs-config-show.txt && \
grep -q '^workspace.status = none' /tmp/meridian-qs-config-show.txt && \
echo "PASS: first-run bootstrap created runtime state only and show works" || echo "FAIL: first-run bootstrap or config show output was unexpected"
```

### QS-4. Models list [CRITICAL]

```bash
uv run meridian --json models list >/tmp/meridian-qs-models.txt 2>&1 && \
grep -Eq 'MODEL|gpt-|claude-|gemini-' /tmp/meridian-qs-models.txt && \
echo "PASS: models list returned catalog data" || echo "FAIL: models list output was unexpected"
```

### QS-4b. Models list --show-superseded [IMPORTANT]

Verifies that `--show-superseded` returns more models than the default view (superseded models are hidden by default).

```bash
DEFAULT_COUNT="$(uv run meridian models list 2>/dev/null | tail -n +2 | wc -l)"
SUPERSEDED_COUNT="$(uv run meridian models list --show-superseded 2>/dev/null | tail -n +2 | wc -l)"
[ "$SUPERSEDED_COUNT" -ge "$DEFAULT_COUNT" ] && \
echo "PASS: --show-superseded shows >= default count ($SUPERSEDED_COUNT >= $DEFAULT_COUNT)" || \
echo "FAIL: --show-superseded ($SUPERSEDED_COUNT) should show >= default ($DEFAULT_COUNT)"
```

### QS-5. Doctor [CRITICAL]

```bash
uv run meridian doctor >/tmp/meridian-qs-doctor.txt && \
grep -q '^ok:' /tmp/meridian-qs-doctor.txt && \
grep -q '^repo_root:' /tmp/meridian-qs-doctor.txt && \
echo "PASS: doctor returned health data" || echo "FAIL: doctor output was unexpected"
```

### QS-6. Spawn dry-run [CRITICAL]

```bash
uv run meridian --json spawn -a reviewer -p "quick sanity prompt" --dry-run > /tmp/meridian-qs-dryrun.json && \
uv run python - <<'PY'
import json
doc = json.load(open("/tmp/meridian-qs-dryrun.json"))
assert doc["status"] == "dry-run"
assert "quick sanity prompt" in doc["composed_prompt"]
assert isinstance(doc["cli_command"], list) and doc["cli_command"]
print("PASS: spawn dry-run produced a composed prompt")
PY
```

### QS-7. Unknown command [IMPORTANT]

```bash
if uv run meridian nonexistent >/tmp/meridian-qs-unknown.out 2>&1; then
  echo "FAIL: unknown command unexpectedly succeeded"
elif grep -q "Unknown command" /tmp/meridian-qs-unknown.out; then
  echo "PASS: unknown command fails cleanly"
else
  echo "FAIL: unknown command error text was not useful"
fi
```

### QS-8. Spawn list [IMPORTANT]

```bash
uv run meridian --json spawn list >/tmp/meridian-qs-spawn-list.txt && \
(uv run python - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("/tmp/meridian-qs-spawn-list.txt").read_text(encoding="utf-8"))
assert isinstance(payload, dict)
assert "spawns" in payload
assert isinstance(payload["spawns"], list)
PY
) && \
echo "PASS: spawn list returned a clean response" || echo "FAIL: spawn list output was unexpected"
```

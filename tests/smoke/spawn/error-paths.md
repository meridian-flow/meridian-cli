# Spawn Error Paths

These checks target predictable failure modes for spawn-related commands. The goal is not success; the goal is a clean, informative failure with no traceback.

## Setup

```bash
export REPO_ROOT=/abs/path/to/meridian-channel
export SMOKE_REPO="$(mktemp -d /tmp/meridian-spawn-errors.XXXXXX)"
git -C "$SMOKE_REPO" init --quiet
for var in $(env | awk -F= '/^MERIDIAN_/ {print $1}'); do unset "$var"; done
export MERIDIAN_REPO_ROOT="$SMOKE_REPO"
export MERIDIAN_STATE_ROOT="$SMOKE_REPO/.meridian"
mkdir -p "$SMOKE_REPO/.agents/agents"
cat > "$SMOKE_REPO/.agents/agents/reviewer.md" <<'EOF'
# Reviewer

Error-path smoke reviewer.
EOF
cd "$REPO_ROOT"
test -d "$SMOKE_REPO/.git" && echo "PASS: spawn error-path repo ready" || echo "FAIL: spawn error-path repo setup failed"
```

### ERR-1. Unknown model is rejected [IMPORTANT]

```bash
if uv run meridian --json spawn -a reviewer -p "bad model" -m definitely-not-a-model --dry-run >/tmp/meridian-spawn-bad-model.out 2>&1; then
  echo "FAIL: bad model unexpectedly succeeded"
elif grep -q "Traceback" /tmp/meridian-spawn-bad-model.out; then
  echo "FAIL: bad model produced a traceback"
else
  echo "PASS: bad model failed cleanly"
fi
```

### ERR-2. Invalid spawn id is rejected [IMPORTANT]

```bash
if uv run meridian --json spawn show no-such-spawn >/tmp/meridian-spawn-bad-id.out 2>&1; then
  echo "FAIL: invalid spawn id unexpectedly succeeded"
elif grep -q "Traceback" /tmp/meridian-spawn-bad-id.out; then
  echo "FAIL: invalid spawn id produced a traceback"
else
  echo "PASS: invalid spawn id failed cleanly"
fi
```

### ERR-3. Empty prompt on a real spawn is graceful [IMPORTANT]

```bash
if uv run meridian --json spawn -a reviewer -p "" >/tmp/meridian-spawn-empty-real.out 2>&1; then
  if grep -q "Traceback" /tmp/meridian-spawn-empty-real.out; then
    echo "FAIL: empty real spawn crashed"
  else
    echo "PASS: empty real spawn was accepted"
  fi
else
  if grep -q "Traceback" /tmp/meridian-spawn-empty-real.out; then
    echo "FAIL: empty real spawn crashed"
  else
    echo "PASS: empty real spawn failed cleanly"
  fi
fi
```

### ERR-4. Batch error paths stay traceback-free [CRITICAL]

```bash
FAILURES=0
for cmd in \
  'uv run meridian nonexistent' \
  'uv run meridian config get does.not.exist' \
  'uv run meridian --json spawn show no-such-spawn' \
  'uv run meridian --json spawn -a reviewer -p test -m definitely-not-a-model --dry-run'
do
  if eval "$cmd" 2>&1 | grep -q 'Traceback'; then
    FAILURES=$((FAILURES + 1))
  fi
done
[ "$FAILURES" -eq 0 ] && echo "PASS: error paths stayed traceback-free" || echo "FAIL: $FAILURES traceback(s) found"
```

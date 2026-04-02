# Agent Mode

Agent mode should narrow the visible CLI surface and switch default output to machine-readable JSON. These checks are small but important because subagents rely on this contract.

## Setup

```bash
export REPO_ROOT=/abs/path/to/meridian-channel
export SMOKE_REPO="$(mktemp -d /tmp/meridian-agent-mode.XXXXXX)"
git -C "$SMOKE_REPO" init --quiet
for var in $(env | awk -F= '/^MERIDIAN_/ {print $1}'); do unset "$var"; done
export MERIDIAN_REPO_ROOT="$SMOKE_REPO"
export MERIDIAN_STATE_ROOT="$SMOKE_REPO/.meridian"
cd "$REPO_ROOT"
test -d "$SMOKE_REPO/.git" && echo "PASS: agent-mode repo ready" || echo "FAIL: agent-mode repo setup failed"
```

### AGT-1. Agent help is restricted [IMPORTANT]

```bash
MERIDIAN_DEPTH=1 uv run meridian --help > /tmp/meridian-agent-help.txt && \
uv run python - <<'PY'
text = open("/tmp/meridian-agent-help.txt").read()
for visible in ("spawn", "work", "models"):
    assert visible in text
for hidden in ("config", "doctor", "init", "session", "completion", "serve", "claude", "codex", "opencode"):
    assert hidden not in text
print("PASS: agent-mode help is restricted")
PY
```

### AGT-2. `--human` restores the full help surface [IMPORTANT]

```bash
MERIDIAN_DEPTH=1 uv run meridian --human --help > /tmp/meridian-agent-human-help.txt && \
uv run python - <<'PY'
text = open("/tmp/meridian-agent-human-help.txt").read()
for visible in ("config", "doctor", "init", "session", "spawn", "work", "claude", "codex", "opencode", "serve"):
    assert visible in text
print("PASS: --human restored full help")
PY
```

### AGT-3. Agent mode keeps structured output on normal commands [IMPORTANT]

```bash
MERIDIAN_DEPTH=1 uv run meridian models list > /tmp/meridian-agent-models.out && \
uv run python - <<'PY'
import json
for line in open("/tmp/meridian-agent-models.out"):
    line = line.strip()
    if line:
        json.loads(line)
print("PASS: agent mode kept structured output")
PY
```

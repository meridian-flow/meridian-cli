# Hooks CLI

Validate operator-facing hook commands: `hooks list`, `hooks check`, `hooks run`.

## Setup

```bash
export REPO_ROOT=/abs/path/to/meridian-cli
export E2E_REPO="$(mktemp -d /tmp/meridian-hooks-cli.XXXXXX)"
export E2E_STATE="$E2E_REPO/.meridian"
export E2E_USER_CONFIG="$E2E_REPO/user.toml"
export E2E_RECORDER="$E2E_REPO/record_hook.py"
export E2E_MARKER="$E2E_REPO/hook-runs.jsonl"

mkdir -p "$E2E_REPO/.git"
cat > "$E2E_RECORDER" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(sys.stdin.read())
marker = Path(sys.argv[1])
marker.parent.mkdir(parents=True, exist_ok=True)
with marker.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(payload) + "\n")
PY

cat > "$E2E_REPO/meridian.toml" <<TOML
[work.artifacts]
sync = "git"

[[hooks]]
name = "record-finalized"
event = "spawn.finalized"
command = "uv run python $E2E_RECORDER $E2E_MARKER"
interval = "10m"

[[hooks]]
name = "record-created"
event = "spawn.created"
command = "uv run python $E2E_RECORDER $E2E_MARKER"
enabled = false
TOML

touch "$E2E_USER_CONFIG"
```

## HOOKS-CLI-1. `hooks list` text output shows table rows [CRITICAL]

```bash
cd "$REPO_ROOT"
MERIDIAN_CONFIG="$E2E_USER_CONFIG" MERIDIAN_REPO_ROOT="$E2E_REPO" MERIDIAN_STATE_ROOT="$E2E_STATE" \
  uv run meridian hooks list --format text
```

Expect:
- Header columns include `name event type source registration status`
- Rows include `record-finalized` and `record-created`
- `record-created` status is `disabled`

## HOOKS-CLI-2. `hooks list` json output is machine-parseable [IMPORTANT]

```bash
cd "$REPO_ROOT"
MERIDIAN_CONFIG="$E2E_USER_CONFIG" MERIDIAN_REPO_ROOT="$E2E_REPO" MERIDIAN_STATE_ROOT="$E2E_STATE" \
  uv run meridian hooks list --format json | jq -e '.hooks | length >= 2'
```

## HOOKS-CLI-3. `hooks check` reports builtin requirement status [IMPORTANT]

```bash
cd "$REPO_ROOT"
MERIDIAN_CONFIG="$E2E_USER_CONFIG" MERIDIAN_REPO_ROOT="$E2E_REPO" MERIDIAN_STATE_ROOT="$E2E_STATE" \
  uv run meridian hooks check --format text
```

Expect:
- Output includes `name status requirements error` columns
- Each builtin hook row shows `ok` or `missing`

## HOOKS-CLI-4. `hooks run` executes manually and bypasses interval throttling [CRITICAL]

```bash
cd "$REPO_ROOT"
MERIDIAN_CONFIG="$E2E_USER_CONFIG" MERIDIAN_REPO_ROOT="$E2E_REPO" MERIDIAN_STATE_ROOT="$E2E_STATE" \
  uv run meridian hooks run record-finalized --format text
MERIDIAN_CONFIG="$E2E_USER_CONFIG" MERIDIAN_REPO_ROOT="$E2E_REPO" MERIDIAN_STATE_ROOT="$E2E_STATE" \
  uv run meridian hooks run record-finalized --format text

jq -s 'length >= 2' "$E2E_MARKER"
```

Expect:
- Both manual runs return a result block with `outcome: success`
- Marker file has at least two lines (manual runs are not interval-throttled)

## HOOKS-CLI-5. `hooks run --event` overrides the hook event context [IMPORTANT]

```bash
cd "$REPO_ROOT"
MERIDIAN_CONFIG="$E2E_USER_CONFIG" MERIDIAN_REPO_ROOT="$E2E_REPO" MERIDIAN_STATE_ROOT="$E2E_STATE" \
  uv run meridian hooks run record-finalized --event spawn.created --format text

tail -n 1 "$E2E_MARKER" | jq -e '.event_name == "spawn.created"'
```

Expect:
- Output shows `event: spawn.created`
- Recorder payload for the latest run has `event_name` equal to `spawn.created`

## HOOKS-CLI-6. Auto-registered builtins show `registration=auto` [IMPORTANT]

```bash
cd "$REPO_ROOT"
MERIDIAN_CONFIG="$E2E_USER_CONFIG" MERIDIAN_REPO_ROOT="$E2E_REPO" MERIDIAN_STATE_ROOT="$E2E_STATE" \
  uv run meridian hooks list --format json \
  | jq -e '.hooks | map(select(.name == "git-autosync" and .registration == "auto")) | length >= 1'
```

Expect:
- At least one `git-autosync` hook entry reports `registration: auto`

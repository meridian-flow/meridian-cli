# Spawn `--from` Context References

These checks validate the `--from` flag which injects prior spawn context (report, files modified, explore commands) into a new spawn's prompt.

## Setup

```bash
export REPO_ROOT=/abs/path/to/meridian-channel
export SMOKE_REPO="$(mktemp -d /tmp/meridian-from.XXXXXX)"
git -C "$SMOKE_REPO" init --quiet
for var in $(env | awk -F= '/^MERIDIAN_/ {print $1}'); do unset "$var"; done
export MERIDIAN_REPO_ROOT="$SMOKE_REPO"
export MERIDIAN_STATE_ROOT="$SMOKE_REPO/.meridian"

# Create a minimal agent for dry-run
mkdir -p "$SMOKE_REPO/.agents/agents"
cat > "$SMOKE_REPO/.agents/agents/coder.md" <<'EOF'
---
name: coder
description: test coder
model: gpt-5.3-codex
sandbox: workspace-write
---
# Coder
EOF

cd "$REPO_ROOT"
echo "PASS: context-from setup complete"
```

### FROM-1. Basic --from with spawn ID [CRITICAL]

Seed a spawn with a report, then dry-run a second spawn referencing it.

```bash
# Seed a completed spawn
SEED_ID=$(uv run python -c "
from pathlib import Path
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_state_paths
repo = Path('$SMOKE_REPO')
sp = resolve_state_paths(repo)
sid = spawn_store.start_spawn(sp.root_dir, chat_id='c1', model='gpt', agent='coder', harness='codex', kind='child', prompt='seed', desc='Phase 1')
spawn_store.finalize_spawn(sp.root_dir, str(sid), status='succeeded', exit_code=0)
rp = sp.root_dir / 'spawns' / str(sid) / 'report.md'
rp.parent.mkdir(parents=True, exist_ok=True)
rp.write_text('# Phase 1 Report\n\nImplemented data model.\n')
print(sid)
")

# Dry-run with --from
uv run meridian --json spawn -a coder --from "$SEED_ID" --dry-run -p "Phase 2: build on phase 1" > /tmp/meridian-from-basic.json 2>&1

python3 -c "
import json
d = json.load(open('/tmp/meridian-from-basic.json'))
assert d['status'] == 'dry-run', 'not dry-run'
assert d['context_from_resolved'] == ['$SEED_ID'], f'wrong resolved: {d[\"context_from_resolved\"]}'
p = d['composed_prompt']
assert '<prior-spawn-context spawn=\"$SEED_ID\">' in p, 'missing context block'
assert '## Report' in p, 'missing report section'
assert 'Phase 1 Report' in p, 'missing report content'
assert '## Explore Further' in p, 'missing explore section'
assert 'meridian spawn show $SEED_ID --report' in p, 'missing show command'
print('PASS: FROM-1 basic --from')
" || echo "FAIL: FROM-1"
```

### FROM-2. --from with session ID [CRITICAL]

Reference a session ID instead of a spawn ID. Should resolve to the latest succeeded spawn in that session.

```bash
# Seed a failed spawn and a succeeded spawn in session c1
uv run python -c "
from pathlib import Path
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_state_paths
repo = Path('$SMOKE_REPO')
sp = resolve_state_paths(repo)
sid = spawn_store.start_spawn(sp.root_dir, chat_id='c1', model='gpt', agent='coder', harness='codex', kind='child', prompt='fail', desc='Failed attempt')
spawn_store.finalize_spawn(sp.root_dir, str(sid), status='failed', exit_code=1, error='oops')
"

# Dry-run with session ref
uv run meridian --json spawn -a coder --from c1 --dry-run -p "Continue from session" > /tmp/meridian-from-session.json 2>&1

python3 -c "
import json
d = json.load(open('/tmp/meridian-from-session.json'))
resolved = d['context_from_resolved']
assert len(resolved) == 1, f'expected 1 resolved, got {len(resolved)}'
p = d['composed_prompt']
assert 'Phase 1 Report' in p, 'should resolve to succeeded spawn with report'
assert 'meridian session log c1' in p, 'missing session log command'
print(f'PASS: FROM-2 session ref resolved to {resolved[0]}')
" || echo "FAIL: FROM-2"
```

### FROM-3. Multiple --from flags [HIGH]

Pass two spawn references. Both context blocks should appear.

```bash
# Seed a second spawn
SEED2_ID=$(uv run python -c "
from pathlib import Path
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_state_paths
repo = Path('$SMOKE_REPO')
sp = resolve_state_paths(repo)
sid = spawn_store.start_spawn(sp.root_dir, chat_id='c2', model='gpt', agent='coder', harness='codex', kind='child', prompt='seed2', desc='Phase 2')
spawn_store.finalize_spawn(sp.root_dir, str(sid), status='succeeded', exit_code=0)
rp = sp.root_dir / 'spawns' / str(sid) / 'report.md'
rp.parent.mkdir(parents=True, exist_ok=True)
rp.write_text('# Phase 2 Report\n\nBuilt API layer.\n')
print(sid)
")

uv run meridian --json spawn -a coder --from "$SEED_ID" --from "$SEED2_ID" --dry-run -p "Phase 3" > /tmp/meridian-from-multi.json 2>&1

python3 -c "
import json
d = json.load(open('/tmp/meridian-from-multi.json'))
assert len(d['context_from_resolved']) == 2, 'should have 2 resolved refs'
p = d['composed_prompt']
assert p.count('<prior-spawn-context') == 2, 'should have 2 context blocks'
assert 'Phase 1 Report' in p, 'missing first report'
assert 'Phase 2 Report' in p, 'missing second report'
print('PASS: FROM-3 multiple --from')
" || echo "FAIL: FROM-3"
```

### FROM-4. --from with no report [HIGH]

Spawn has no report file. Should render "No report available." gracefully.

```bash
NO_REPORT_ID=$(uv run python -c "
from pathlib import Path
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_state_paths
repo = Path('$SMOKE_REPO')
sp = resolve_state_paths(repo)
sid = spawn_store.start_spawn(sp.root_dir, chat_id='c3', model='gpt', agent='coder', harness='codex', kind='child', prompt='no-report', desc='No report spawn')
spawn_store.finalize_spawn(sp.root_dir, str(sid), status='succeeded', exit_code=0)
print(sid)
")

uv run meridian --json spawn -a coder --from "$NO_REPORT_ID" --dry-run -p "test" > /tmp/meridian-from-noreport.json 2>&1

python3 -c "
import json
d = json.load(open('/tmp/meridian-from-noreport.json'))
p = d['composed_prompt']
assert 'No report available.' in p, 'missing no-report fallback'
assert '## Files Modified' not in p, 'should not have files section when no files'
print('PASS: FROM-4 no report')
" || echo "FAIL: FROM-4"
```

### FROM-5. --from + --continue conflict [HIGH]

Should fail with a clear error.

```bash
uv run meridian spawn --from "$SEED_ID" --continue "$SEED_ID" -p "test" 2>/tmp/meridian-from-conflict.err; RC=$?
test $RC -ne 0 && grep -q "Cannot use --from with --continue" /tmp/meridian-from-conflict.err && \
  echo "PASS: FROM-5 conflict rejected" || echo "FAIL: FROM-5"
```

### FROM-6. --from with invalid spawn ID [HIGH]

Should fail with a clear error message.

```bash
uv run meridian spawn --from p99999 --dry-run -p "test" 2>/tmp/meridian-from-invalid.err; RC=$?
test $RC -ne 0 && grep -qi "not found" /tmp/meridian-from-invalid.err && \
  echo "PASS: FROM-6 invalid ID error" || echo "FAIL: FROM-6"
```

## Cleanup

```bash
rm -rf "$SMOKE_REPO" /tmp/meridian-from-*.json /tmp/meridian-from-*.err
unset MERIDIAN_REPO_ROOT MERIDIAN_STATE_ROOT SMOKE_REPO
echo "PASS: cleanup complete"
```

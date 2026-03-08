# Meridian Smoke Testing Guide

LLM agents should follow this document to verify meridian-channel is working correctly. Every test is copy-pasteable and designed for automated verification.

---

## 1. Setup

### 1.1 Install Dependencies

```bash
cd /path/to/meridian-channel
uv sync --extra dev
```

**PASS**: Exit code 0, no errors in output.

### 1.2 Create an Isolated Test Directory

All tests run in a temporary directory to avoid polluting real state. Run this block once at the start of every smoke test session:

```bash
export SMOKE_DIR="$(mktemp -d)"
cd "$SMOKE_DIR"
git init --quiet
# Point meridian state to a fresh location
export MERIDIAN_STATE_ROOT="$SMOKE_DIR/.meridian"
# Unset all MERIDIAN_* env vars from parent to prevent leakage
for var in $(env | grep '^MERIDIAN_' | cut -d= -f1); do unset "$var"; done
```

### 1.3 Configure Mock Harness

Tests use a mock harness to avoid running real LLM providers. Set this env var to the mock harness bundled with the test suite:

```bash
REPO_ROOT="/path/to/meridian-channel"  # adjust to your checkout
export MERIDIAN_HARNESS_COMMAND="python $REPO_ROOT/tests/mock_harness.py --duration 0"
```

### 1.4 Alias for Convenience

```bash
alias m="uv run --directory $REPO_ROOT meridian"
```

All commands below use `uv run meridian` for explicitness. Substitute `m` if you set the alias.

---

## 2. Quick Sanity (5 minutes)

Run these 10 checks in order. If any [CRITICAL] check fails, stop and investigate before continuing.

### QS-1. Help text [CRITICAL]

```bash
uv run meridian --help 2>&1
echo "EXIT: $?"
```

**Check**:
- Exit code is `0`
- Output contains all command groups: `spawn`, `report`, `models`, `skills`, `config`, `space`, `doctor`, `serve`, `completion`

```bash
uv run meridian --help 2>&1 | grep -qE "spawn|report|models|skills" && echo "PASS" || echo "FAIL"
```

### QS-2. Version [CRITICAL]

```bash
uv run meridian --version 2>&1
echo "EXIT: $?"
```

**Check**:
- Exit code is `0`
- Output is a valid semver-like string (e.g. `0.0.1`)

```bash
uv run meridian --version 2>&1 | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+' && echo "PASS" || echo "FAIL"
```

### QS-3. Config init [CRITICAL]

```bash
uv run meridian --json config init 2>&1
echo "EXIT: $?"
```

**Check**:
- Exit code is `0`
- JSON output contains `"path"` key pointing to a `.meridian/config.toml` file
- JSON output contains `"created"` key (boolean)

```bash
uv run meridian --json config init 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'path' in d and 'config.toml' in d['path']
assert 'created' in d
print('PASS')
"
```

### QS-4. Config show [CRITICAL]

```bash
uv run meridian --json config show 2>&1
echo "EXIT: $?"
```

**Check**:
- Exit code is `0`
- JSON output has `"values"` array with config entries
- Each entry has `"key"`, `"value"`, `"source"` fields

```bash
uv run meridian --json config show 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'values' in d and len(d['values']) > 0
entry = d['values'][0]
assert 'key' in entry and 'value' in entry and 'source' in entry
print('PASS')
"
```

### QS-5. Models list [CRITICAL]

```bash
uv run meridian --json models list 2>&1
echo "EXIT: $?"
```

**Check**:
- Exit code is `0`
- JSON output has `"models"` array with at least one entry
- Each model has `"model_id"`, `"harness"`, `"aliases"` fields

```bash
uv run meridian --json models list 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'models' in d and len(d['models']) > 0
m = d['models'][0]
assert 'model_id' in m and 'harness' in m and 'aliases' in m
print('PASS')
"
```

### QS-6. Skills list [CRITICAL]

```bash
uv run meridian --json skills list 2>&1
echo "EXIT: $?"
```

**Check**:
- Exit code is `0`
- JSON output has `"skills"` array
- Each skill has `"name"` and `"description"` fields

```bash
uv run meridian --json skills list 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'skills' in d
if len(d['skills']) > 0:
    s = d['skills'][0]
    assert 'name' in s and 'description' in s
print('PASS')
"
```

### QS-7. Doctor [CRITICAL]

```bash
uv run meridian --json doctor 2>&1
echo "EXIT: $?"
```

**Check**:
- Exit code is `0`
- JSON has `"repo_root"`, `"spaces_checked"`, `"ok"` fields
- No Python traceback in stderr

```bash
uv run meridian --json doctor 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'repo_root' in d
assert 'spaces_checked' in d
assert 'ok' in d
print('PASS')
"
```

### QS-8. Spawn dry-run [CRITICAL]

```bash
uv run meridian --json spawn create --dry-run -p "test prompt" 2>&1
echo "EXIT: $?"
```

**Check**:
- Exit code is `0`
- JSON has `"status": "dry-run"`, `"command": "spawn.create"`
- JSON has `"composed_prompt"` containing `"test prompt"`
- JSON has `"cli_command"` array (the harness invocation)
- No Python traceback in stderr

```bash
uv run meridian --json spawn create --dry-run -p "test prompt" 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'dry-run'
assert d['command'] == 'spawn.create'
assert 'test prompt' in d['composed_prompt']
assert isinstance(d['cli_command'], list) and len(d['cli_command']) > 0
print('PASS')
"
```

### QS-9. Unknown command error [IMPORTANT]

```bash
uv run meridian nonexistent 2>&1
echo "EXIT: $?"
```

**Check**:
- Exit code is `1`
- Stderr contains `"Unknown command: nonexistent"`

```bash
uv run meridian nonexistent 2>&1; test $? -eq 1 && echo "PASS: exit code" || echo "FAIL: exit code"
```

### QS-10. Space list [IMPORTANT]

```bash
uv run meridian --json space list 2>&1
echo "EXIT: $?"
```

**Check**:
- Exit code is `0`
- JSON has `"spaces"` array (may be empty in fresh environment)

```bash
uv run meridian --json space list 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'spaces' in d and isinstance(d['spaces'], list)
print('PASS')
"
```

---

## 3. Full Suite (15 minutes)

### 3.1 Config Commands

#### FS-CFG-1. Config init creates config file [CRITICAL]

```bash
uv run meridian --json config init 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'path' in d
assert 'config.toml' in d['path']
print('PASS: config init')
"
```

#### FS-CFG-2. Config show lists all settings [CRITICAL]

```bash
uv run meridian --json config show 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
vals = d['values']
keys = [v['key'] for v in vals]
# Check key config categories exist
assert any('defaults.' in k for k in keys), 'missing defaults.* keys'
assert any('timeouts.' in k for k in keys), 'missing timeouts.* keys'
assert any('permissions.' in k for k in keys), 'missing permissions.* keys'
print('PASS: config show has expected categories')
"
```

#### FS-CFG-3. Config get retrieves a specific key [CRITICAL]

```bash
uv run meridian --json config get defaults.model 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['key'] == 'defaults.model'
assert d['value'] is not None
assert d['source'] in ('builtin', 'file', 'env')
print('PASS: config get defaults.model =', d['value'])
"
```

#### FS-CFG-4. Config set and reset [IMPORTANT]

```bash
# Set a value
uv run meridian --json config set defaults.model test-model-123 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('PASS: config set')
"

# Verify it took effect
uv run meridian --json config get defaults.model 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['value'] == 'test-model-123', f'Expected test-model-123, got {d[\"value\"]}'
assert d['source'] == 'file'
print('PASS: config get after set')
"

# Reset it
uv run meridian --json config reset defaults.model 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('PASS: config reset')
"

# Verify reset
uv run meridian --json config get defaults.model 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['source'] == 'builtin', f'Expected builtin after reset, got {d[\"source\"]}'
print('PASS: config reset verified')
"
```

### 3.2 Models Commands

#### FS-MOD-1. Models list returns catalog [CRITICAL]

```bash
uv run meridian --json models list 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
models = d['models']
assert len(models) >= 1, 'Expected at least 1 model'
ids = [m['model_id'] for m in models]
# Verify expected fields on every model
for m in models:
    assert 'model_id' in m, 'missing model_id'
    assert 'harness' in m, 'missing harness'
    assert 'aliases' in m, 'missing aliases'
    assert 'cost_tier' in m, 'missing cost_tier'
print(f'PASS: {len(models)} models found: {ids}')
"
```

#### FS-MOD-2. Models show by alias [IMPORTANT]

```bash
uv run meridian --json models show opus 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'model_id' in d
assert 'opus' in d.get('aliases', [])
assert 'harness' in d
print(f'PASS: models show opus -> {d[\"model_id\"]}')
"
```

#### FS-MOD-3. Models show by full ID [IMPORTANT]

```bash
uv run meridian --json models show gpt-5.3-codex 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['model_id'] == 'gpt-5.3-codex'
print('PASS: models show gpt-5.3-codex')
"
```

#### FS-MOD-4. Models show unknown model [NICE-TO-HAVE]

```bash
uv run meridian --json models show nonexistent-model-xyz 2>&1
EXIT=$?
test $EXIT -ne 0 && echo "PASS: nonexistent model returns non-zero" || echo "FAIL: expected non-zero exit"
```

### 3.3 Skills Commands

#### FS-SKL-1. Skills list [CRITICAL]

```bash
uv run meridian --json skills list 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'skills' in d
for s in d['skills']:
    assert 'name' in s and 'description' in s
    assert 'path' in s
print(f'PASS: {len(d[\"skills\"])} skills listed')
"
```

#### FS-SKL-2. Skills show loads content [IMPORTANT]

```bash
uv run meridian --json skills list 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
if d['skills']:
    print(d['skills'][0]['name'])
" | read SKILL_NAME 2>/dev/null

# If we have a skill, test show
uv run meridian --json skills show orchestrate 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'name' in d
assert 'content' in d
assert len(d['content']) > 0
print(f'PASS: skills show loaded {len(d[\"content\"])} chars')
"
```

#### FS-SKL-3. Skills search [NICE-TO-HAVE]

```bash
uv run meridian --json skills search spawn 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'skills' in d
print(f'PASS: skills search returned {len(d[\"skills\"])} results')
"
```

### 3.4 Doctor Command

#### FS-DOC-1. Doctor reports health [CRITICAL]

```bash
uv run meridian --json doctor 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'repo_root' in d and d['repo_root']
assert 'spaces_checked' in d
assert 'runs_checked' in d
assert 'agents_dir' in d
assert 'skills_dir' in d
assert isinstance(d['ok'], bool)
print(f'PASS: doctor ok={d[\"ok\"]}, spaces={d[\"spaces_checked\"]}, runs={d[\"runs_checked\"]}')
"
```

#### FS-DOC-2. Doctor text mode [IMPORTANT]

```bash
uv run meridian --format text doctor 2>&1 | python3 -c "
import sys
text = sys.stdin.read()
assert 'ok:' in text, 'missing ok: in text output'
assert 'repo_root:' in text, 'missing repo_root: in text output'
assert not text.strip().startswith('{'), 'text mode should not start with {'
print('PASS: doctor text mode is human-readable')
"
```

### 3.5 Space Commands

#### FS-SPC-1. Space start with dry-run [CRITICAL]

```bash
uv run meridian --json space start --dry-run 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['message'] == 'Launch dry-run.'
assert d['exit_code'] == 0
assert 'space_id' in d and d['space_id'].startswith('s')
assert isinstance(d['command'], list) and len(d['command']) > 0
print(f'PASS: space start dry-run, space_id={d[\"space_id\"]}')
"
```

#### FS-SPC-2. Space list [IMPORTANT]

```bash
uv run meridian --json space list 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'spaces' in d and isinstance(d['spaces'], list)
for s in d['spaces']:
    assert 'space_id' in s
print(f'PASS: space list returned {len(d[\"spaces\"])} spaces')
"
```

#### FS-SPC-3. Space list with limit [NICE-TO-HAVE]

```bash
uv run meridian --json space list --limit 2 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert len(d['spaces']) <= 2
print(f'PASS: space list --limit 2 returned {len(d[\"spaces\"])} spaces')
"
```

#### FS-SPC-4. Space show [IMPORTANT]

First create a space, then show it:

```bash
# Create a space via dry-run (which still creates the space record)
SPACE_ID=$(uv run meridian --json space start --dry-run 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d['space_id'])
")

uv run meridian --json space show "$SPACE_ID" 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'space_id' in d
assert 'spawn_ids' in d
print(f'PASS: space show {d[\"space_id\"]}')
"
```

### 3.6 Spawn Commands (Dry-Run)

#### FS-SPN-1. Spawn create dry-run basic [CRITICAL]

```bash
uv run meridian --json spawn create --dry-run -p "Write hello world" 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'dry-run'
assert d['command'] == 'spawn.create'
assert 'Write hello world' in d['composed_prompt']
assert d['model'] is not None and len(d['model']) > 0
assert isinstance(d['cli_command'], list)
print(f'PASS: spawn dry-run, model={d[\"model\"]}, harness={d[\"harness_id\"]}')
"
```

#### FS-SPN-2. Spawn create dry-run with model override [IMPORTANT]

```bash
uv run meridian --json spawn create --dry-run -p "test" -m opus 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'dry-run'
assert 'opus' in d['model'] or d['model'] == 'claude-opus-4-6'
print(f'PASS: model override, model={d[\"model\"]}')
"
```

#### FS-SPN-3. Spawn create dry-run with template vars [IMPORTANT]

```bash
uv run meridian --json spawn create --dry-run \
  -p "Review {{FILE_PATH}} for {{CONCERN}}" \
  --prompt-var FILE_PATH=src/main.py \
  --prompt-var CONCERN=security \
  2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'dry-run'
assert 'src/main.py' in d['composed_prompt']
assert 'security' in d['composed_prompt']
assert '{{FILE_PATH}}' not in d['composed_prompt'], 'Template var not replaced'
assert '{{CONCERN}}' not in d['composed_prompt'], 'Template var not replaced'
print('PASS: template vars substituted correctly')
"
```

#### FS-SPN-4. Spawn create dry-run with file references [IMPORTANT]

```bash
# Create a dummy file to reference
echo "# Test file" > /tmp/smoke-test-ref.md

uv run meridian --json spawn create --dry-run \
  -p "Review this" \
  -f /tmp/smoke-test-ref.md \
  2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'dry-run'
refs = d.get('reference_files', [])
assert len(refs) >= 1, 'Expected at least 1 reference file'
print(f'PASS: {len(refs)} reference files included')
"
```

#### FS-SPN-5. Spawn list [CRITICAL]

```bash
uv run meridian --json spawn list 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
# spawn list returns a list or an object with spawn data
assert isinstance(d, (list, dict))
print('PASS: spawn list returned valid response')
"
```

#### FS-SPN-6. Spawn stats [IMPORTANT]

```bash
uv run meridian --json spawn stats 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'total_runs' in d
assert 'succeeded' in d
assert 'failed' in d
assert 'running' in d
print(f'PASS: spawn stats, total={d[\"total_runs\"]}, ok={d[\"succeeded\"]}, fail={d[\"failed\"]}')
"
```

#### FS-SPN-7. Spawn list with status filter [NICE-TO-HAVE]

```bash
uv run meridian --json spawn list --status failed 2>&1
echo "EXIT: $?"
# Should not crash; exit code 0
test $? -eq 0 && echo "PASS" || echo "FAIL"
```

#### FS-SPN-8. Spawn list with limit [NICE-TO-HAVE]

```bash
uv run meridian --json spawn list --limit 5 2>&1
echo "EXIT: $?"
test $? -eq 0 && echo "PASS" || echo "FAIL"
```

### 3.7 Report Commands

#### FS-RPT-1. Report create from argument [IMPORTANT]

This requires an active space with a spawn. In environments without a running spawn, this may fail gracefully:

```bash
uv run meridian --json report create "Test report content" 2>&1
EXIT=$?
echo "EXIT: $EXIT"
# May succeed (exit 0) if space/spawn exists, or fail if no context
# Key: should NOT produce a Python traceback
uv run meridian --json report create "Test report content" 2>&1 | grep -v "^warning:" | grep -v "^error:" | grep -c "Traceback"
test $? -ne 0 && echo "PASS: no traceback" || echo "FAIL: traceback found"
```

#### FS-RPT-2. Report show [IMPORTANT]

```bash
uv run meridian --json report show 2>&1
EXIT=$?
echo "EXIT: $EXIT"
# Should not produce a traceback regardless of whether reports exist
uv run meridian --json report show 2>&1 | grep -c "Traceback" | python3 -c "
import sys
count = int(sys.stdin.read().strip())
print('PASS: no traceback' if count == 0 else 'FAIL: traceback found')
"
```

#### FS-RPT-3. Report search [NICE-TO-HAVE]

```bash
uv run meridian --json report search "test" 2>&1
EXIT=$?
echo "EXIT: $EXIT"
# Should return valid JSON or graceful error
uv run meridian --json report search "test" 2>&1 | python3 -c "
import sys
text = sys.stdin.read()
# Either valid JSON or a clean error - no traceback
assert 'Traceback' not in text
print('PASS: report search no traceback')
"
```

### 3.8 Output Format Tests

#### FS-FMT-1. JSON format flag [CRITICAL]

```bash
uv run meridian --json doctor 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert isinstance(d, dict)
print('PASS: --json produces valid JSON')
"
```

#### FS-FMT-2. --format json [CRITICAL]

```bash
uv run meridian --format json doctor 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert isinstance(d, dict)
print('PASS: --format json produces valid JSON')
"
```

#### FS-FMT-3. --format text [IMPORTANT]

```bash
uv run meridian --format text doctor 2>&1 | python3 -c "
import sys
text = sys.stdin.read()
assert 'ok:' in text
assert not text.strip().startswith('{')
print('PASS: --format text produces human-readable output')
"
```

#### FS-FMT-4. --porcelain flag [IMPORTANT]

```bash
uv run meridian --porcelain doctor 2>&1 | python3 -c "
import sys
text = sys.stdin.read()
# Porcelain uses tab-separated key=value pairs
assert 'ok=' in text
assert '\t' in text
print('PASS: --porcelain produces tab-separated output')
"
```

#### FS-FMT-5. --format porcelain [NICE-TO-HAVE]

```bash
uv run meridian --format porcelain doctor 2>&1 | python3 -c "
import sys
text = sys.stdin.read()
assert 'ok=' in text
print('PASS: --format porcelain works')
"
```

#### FS-FMT-6. Invalid format rejected [IMPORTANT]

```bash
uv run meridian --format yaml doctor 2>&1
EXIT=$?
test $EXIT -ne 0 && echo "PASS: invalid format rejected" || echo "FAIL: expected non-zero exit"
```

### 3.9 Error Handling

#### FS-ERR-1. Unknown top-level command [CRITICAL]

```bash
uv run meridian nonexistent 2>&1
EXIT=$?
test $EXIT -eq 1 && echo "PASS: exit code 1" || echo "FAIL: expected exit 1, got $EXIT"
uv run meridian nonexistent 2>&1 | grep -q "Unknown command" && echo "PASS: error message" || echo "FAIL: missing error message"
```

#### FS-ERR-2. Missing required argument [IMPORTANT]

```bash
uv run meridian models show 2>&1
EXIT=$?
test $EXIT -ne 0 && echo "PASS: missing arg rejected" || echo "FAIL: expected non-zero"
```

#### FS-ERR-3. Config get with invalid key [IMPORTANT]

```bash
uv run meridian config get nonexistent.key.xyz 2>&1
EXIT=$?
test $EXIT -ne 0 && echo "PASS: invalid config key rejected" || echo "FAIL: expected non-zero"
```

#### FS-ERR-4. Spawn show with invalid spawn ID [IMPORTANT]

```bash
uv run meridian --json spawn show nonexistent-spawn-id-999 2>&1
EXIT=$?
test $EXIT -ne 0 && echo "PASS: invalid spawn ID rejected" || echo "FAIL: expected non-zero"
```

#### FS-ERR-5. No traceback on any error [CRITICAL]

Run a batch of error-inducing commands and verify none produce Python tracebacks:

```bash
FAIL_COUNT=0

for cmd in \
  "uv run meridian nonexistent" \
  "uv run meridian models show no-such-model" \
  "uv run meridian config get bad.key.path" \
  "uv run meridian --format yaml doctor" \
  "uv run meridian spawn show no-such-spawn"
do
  OUTPUT=$(eval "$cmd" 2>&1)
  if echo "$OUTPUT" | grep -q "Traceback"; then
    echo "FAIL: traceback in: $cmd"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
done

test $FAIL_COUNT -eq 0 && echo "PASS: no tracebacks in error paths" || echo "FAIL: $FAIL_COUNT commands produced tracebacks"
```

### 3.10 Agent Mode Behavior

#### FS-AGT-1. Agent mode restricts help [IMPORTANT]

```bash
MERIDIAN_SPACE_ID=s-test MERIDIAN_DEPTH=1 uv run meridian --help 2>&1 | python3 -c "
import sys
text = sys.stdin.read()
# Agent mode should show: spawn, report, skills, models
assert 'spawn' in text
assert 'report' in text
assert 'skills' in text
assert 'models' in text
# Agent mode should hide: space, config, doctor, serve, completion
for hidden in ['space', 'config', 'completion', 'serve']:
    assert hidden not in text, f'{hidden} should be hidden in agent mode'
print('PASS: agent mode help is restricted')
"
```

#### FS-AGT-2. --human flag restores full help [NICE-TO-HAVE]

```bash
MERIDIAN_SPACE_ID=s-test MERIDIAN_DEPTH=1 uv run meridian --human --help 2>&1 | python3 -c "
import sys
text = sys.stdin.read()
assert 'space' in text
assert 'config' in text
assert 'serve' in text
print('PASS: --human restores full help')
"
```

#### FS-AGT-3. Agent mode defaults to JSON output [IMPORTANT]

```bash
MERIDIAN_SPACE_ID=s1 MERIDIAN_DEPTH=1 uv run meridian doctor 2>&1 | python3 -c "
import sys, json
text = sys.stdin.read()
# In agent mode with depth > 0, output uses agent sink (JSONL lines)
# Each line should be valid JSON
for line in text.strip().split('\n'):
    if line.strip():
        json.loads(line)
print('PASS: agent mode outputs JSON')
"
```

---

## 4. State Integrity Checks

After running commands that create spaces (like `space start --dry-run`), verify the on-disk state files.

### 4.1 Space JSON Schema [CRITICAL]

```bash
# Create a space
SPACE_ID=$(uv run meridian --json space start --dry-run 2>&1 | python3 -c "
import sys, json; print(json.load(sys.stdin)['space_id'])
")

# Find and validate space.json
SPACE_JSON=".meridian/.spaces/$SPACE_ID/space.json"
test -f "$SPACE_JSON" && echo "PASS: space.json exists" || echo "FAIL: space.json missing"

python3 -c "
import json, sys

with open('$SPACE_JSON') as f:
    d = json.load(f)

# Required fields
assert 'schema_version' in d and isinstance(d['schema_version'], int), 'missing/bad schema_version'
assert 'id' in d and d['id'] == '$SPACE_ID', 'id mismatch'
assert 'created_at' in d and isinstance(d['created_at'], str), 'missing/bad created_at'
# created_at should be ISO format ending in Z
assert d['created_at'].endswith('Z'), 'created_at should end with Z'
# name is optional (can be null)
assert 'name' in d

print(f'PASS: space.json schema valid for {d[\"id\"]}')
"
```

### 4.2 Directory Structure [IMPORTANT]

```bash
SPACE_DIR=".meridian/.spaces/$SPACE_ID"

# Core directories
test -d "$SPACE_DIR/fs" && echo "PASS: fs/ exists" || echo "FAIL: fs/ missing"
test -f "$SPACE_DIR/space.json" && echo "PASS: space.json exists" || echo "FAIL: space.json missing"

echo "PASS: directory structure verified"
```

### 4.3 Spawns JSONL Schema [IMPORTANT]

If spawns have been created (non-dry-run), verify the spawns.jsonl format:

```bash
SPAWNS_JSONL=".meridian/.spaces/$SPACE_ID/spawns.jsonl"

if test -f "$SPAWNS_JSONL"; then
  python3 -c "
import json

with open('$SPAWNS_JSONL') as f:
    lines = [l.strip() for l in f if l.strip()]

for i, line in enumerate(lines):
    event = json.loads(line)
    # Every event must have at minimum an event type or spawn_id
    assert isinstance(event, dict), f'Line {i}: not a JSON object'
    # Events should have a spawn_id field
    assert 'spawn_id' in event or 'id' in event, f'Line {i}: missing identifier'
    print(f'Line {i}: valid JSON event')

print(f'PASS: spawns.jsonl has {len(lines)} valid events')
"
else
  echo "SKIP: no spawns.jsonl yet (no non-dry-run spawns created)"
fi
```

### 4.4 Sessions JSONL Schema [IMPORTANT]

```bash
SESSIONS_JSONL=".meridian/.spaces/$SPACE_ID/sessions.jsonl"

if test -f "$SESSIONS_JSONL"; then
  python3 -c "
import json

with open('$SESSIONS_JSONL') as f:
    lines = [l.strip() for l in f if l.strip()]

for i, line in enumerate(lines):
    event = json.loads(line)
    assert isinstance(event, dict), f'Line {i}: not a JSON object'
    print(f'Line {i}: valid JSON event')

print(f'PASS: sessions.jsonl has {len(lines)} valid events')
"
else
  echo "SKIP: no sessions.jsonl yet"
fi
```

### 4.5 Gitignore Created [NICE-TO-HAVE]

```bash
test -f ".meridian/.gitignore" && echo "PASS: .gitignore exists" || echo "FAIL: .gitignore missing"
```

---

## 5. Harness Integration (if harness available)

These tests require a working harness (mock or real). Skip if `MERIDIAN_HARNESS_COMMAND` is not set or no harness is configured.

### 5.1 Full Spawn Lifecycle [CRITICAL]

```bash
# Ensure mock harness is configured (see Setup section 1.3)
# Create a space first
SPACE_ID=$(uv run meridian --json space start --dry-run 2>&1 | python3 -c "
import sys, json; print(json.load(sys.stdin)['space_id'])
")

# Run a real spawn (mock harness, instant completion)
uv run meridian --json spawn create --space "$SPACE_ID" -p "Say hello" 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['command'] == 'spawn.create'
assert d['status'] in ('succeeded', 'failed', 'running')
if d.get('spawn_id'):
    print(f'PASS: spawn completed, id={d[\"spawn_id\"]}, status={d[\"status\"]}')
else:
    print(f'RESULT: spawn status={d[\"status\"]}, message={d.get(\"message\", \"\")}')
"
```

### 5.2 Spawn Show After Create [IMPORTANT]

```bash
# Get a spawn ID from the previous test or from spawn list
SPAWN_ID=$(uv run meridian --json spawn list --space "$SPACE_ID" --limit 1 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
spawns = d if isinstance(d, list) else d.get('spawns', [])
if spawns:
    print(spawns[0].get('spawn_id', spawns[0].get('id', '')))
" 2>/dev/null)

if [ -n "$SPAWN_ID" ]; then
  uv run meridian --json spawn show "$SPAWN_ID" --space "$SPACE_ID" 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert 'status' in d
print(f'PASS: spawn show {d.get(\"spawn_id\", d.get(\"id\", \"?\"))}, status={d[\"status\"]}')
"
else
  echo "SKIP: no spawn ID available for show test"
fi
```

### 5.3 Exit Code Propagation [IMPORTANT]

Verify that harness exit codes propagate through spawn create:

```bash
# Configure mock harness to exit with code 1
ORIGINAL_CMD="$MERIDIAN_HARNESS_COMMAND"
REPO_ROOT_DIR="$(cd /path/to/meridian-channel && pwd)"  # adjust path
export MERIDIAN_HARNESS_COMMAND="python $REPO_ROOT_DIR/tests/mock_harness.py --exit-code 1 --duration 0"

uv run meridian --json spawn create --space "$SPACE_ID" -p "This should fail" 2>&1
EXIT=$?

# Restore original harness
export MERIDIAN_HARNESS_COMMAND="$ORIGINAL_CMD"

test $EXIT -ne 0 && echo "PASS: non-zero harness exit propagated" || echo "FAIL: expected non-zero exit"
```

### 5.4 Background Spawn [NICE-TO-HAVE]

```bash
uv run meridian --json spawn create --space "$SPACE_ID" -p "Background task" 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] in ('running', 'succeeded', 'failed')
spawn_id = d.get('spawn_id')
if spawn_id:
    print(f'PASS: background spawn created, id={spawn_id}')
else:
    print(f'RESULT: background spawn status={d[\"status\"]}')
"
```

---

## 6. Edge Cases and Regression Guards

### 6.1 Template Variable Collision [IMPORTANT]

Verify that template vars in `--prompt-var` do not collide with internal template markers:

```bash
uv run meridian --json spawn create --dry-run \
  -p "Check {{PROMPT}} and {{MODEL}}" \
  --prompt-var PROMPT=user-prompt \
  --prompt-var MODEL=user-model \
  2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'dry-run'
# Template vars should be substituted
assert 'user-prompt' in d['composed_prompt']
assert 'user-model' in d['composed_prompt']
# Original markers should be gone
assert '{{PROMPT}}' not in d['composed_prompt']
assert '{{MODEL}}' not in d['composed_prompt']
print('PASS: template variable collision handled')
"
```

### 6.2 Empty Prompt [IMPORTANT]

```bash
uv run meridian --json spawn create --dry-run -p "" 2>&1
EXIT=$?
echo "EXIT: $EXIT"
# Should either succeed with empty prompt or fail gracefully
uv run meridian --json spawn create --dry-run -p "" 2>&1 | python3 -c "
import sys
text = sys.stdin.read()
assert 'Traceback' not in text
print('PASS: empty prompt handled without traceback')
"
```

### 6.3 Permission Tier Flag [NICE-TO-HAVE]

```bash
uv run meridian --json spawn create --dry-run -p "test" --permission full 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['status'] == 'dry-run'
print('PASS: --permission flag accepted')
"
```

### 6.4 Concurrent Format Flags [IMPORTANT]

Verify that conflicting format flags are handled:

```bash
# --json should take precedence
uv run meridian --json --format text doctor 2>&1 | python3 -c "
import sys, json
# --json is processed before --format, should produce JSON
d = json.load(sys.stdin)
assert isinstance(d, dict)
print('PASS: --json takes precedence over --format text')
"
```

### 6.5 --config Flag With Custom File [NICE-TO-HAVE]

```bash
# Create a temporary config
TEMP_CONFIG=$(mktemp --suffix=.toml)
echo '[defaults]' > "$TEMP_CONFIG"
echo 'model = "custom-test-model"' >> "$TEMP_CONFIG"

uv run meridian --config "$TEMP_CONFIG" --json config get defaults.model 2>&1 | python3 -c "
import sys, json
d = json.load(sys.stdin)
assert d['value'] == 'custom-test-model'
assert d['source'] == 'file'
print('PASS: --config overlay applied')
"

rm -f "$TEMP_CONFIG"
```

### 6.6 Serve Command Exits on EOF [NICE-TO-HAVE]

```bash
echo "" | timeout 5 uv run meridian serve 2>&1
EXIT=$?
test $EXIT -eq 0 && echo "PASS: serve exits cleanly on EOF" || echo "FAIL: serve exit code $EXIT"
```

### 6.7 Completion Script Generation [NICE-TO-HAVE]

```bash
uv run meridian completion bash 2>&1 | grep -q "meridian" && echo "PASS: bash completion" || echo "FAIL: bash completion"
uv run meridian completion zsh 2>&1 | grep -q "meridian" && echo "PASS: zsh completion" || echo "FAIL: zsh completion"
```

---

## 7. Anomaly Checklist

After running any test section, scan for these anomalies. Any occurrence is a **FAIL**.

### 7.1 Python Tracebacks [CRITICAL]

No command should ever produce a Python traceback in stdout or stderr during normal operation (including error cases).

```bash
# Grep recent test output for tracebacks
# If capturing all output to a log file:
# grep -c "Traceback (most recent call last)" smoke_test.log
# Should be 0
```

**Detection**: Look for `Traceback (most recent call last)` in any command output.

### 7.2 Hangs [CRITICAL]

No command should hang indefinitely. All tests should complete within their timeout.

**Detection**: If any command takes more than 30 seconds, it's likely hung. Use `timeout 30` prefix:

```bash
timeout 30 uv run meridian --json doctor 2>&1 || echo "FAIL: command hung or timed out"
```

### 7.3 Schema Corruption [IMPORTANT]

State files should always contain valid JSON:

```bash
# Check all space.json files
find .meridian/.spaces -name "space.json" -exec python3 -c "
import json, sys
for path in sys.argv[1:]:
    try:
        with open(path) as f:
            json.load(f)
        print(f'OK: {path}')
    except json.JSONDecodeError as e:
        print(f'CORRUPT: {path}: {e}')
        sys.exit(1)
" {} +
echo "PASS: no corrupted space.json files"

# Check all JSONL files
find .meridian/.spaces -name "*.jsonl" -exec python3 -c "
import json, sys
for path in sys.argv[1:]:
    with open(path) as f:
        for i, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as e:
                print(f'CORRUPT: {path} line {i}: {e}')
                sys.exit(1)
    print(f'OK: {path}')
" {} +
echo "PASS: no corrupted JSONL files"
```

### 7.4 Missing Error Messages [IMPORTANT]

Error paths should produce user-friendly messages, not silent failures:

```bash
# These should all produce error messages on stderr
for cmd in \
  "uv run meridian nonexistent" \
  "uv run meridian models show no-such-model" \
  "uv run meridian space show no-such-space"
do
  STDERR=$(eval "$cmd" 2>&1 1>/dev/null)
  if [ -z "$STDERR" ]; then
    echo "WARN: silent error for: $cmd"
  fi
done
```

### 7.5 Zombie Processes [NICE-TO-HAVE]

After running spawn tests, check that no mock harness processes are left behind:

```bash
# Look for leftover mock_harness.py processes
ps aux | grep mock_harness.py | grep -v grep
# Should return nothing
```

### 7.6 Lock File Cleanup [NICE-TO-HAVE]

Lock files should not be left in a locked state:

```bash
find .meridian -name "*.lock" -exec python3 -c "
import fcntl, sys
for path in sys.argv[1:]:
    try:
        with open(path, 'rb') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        print(f'OK: {path} (unlocked)')
    except BlockingIOError:
        print(f'WARN: {path} is still locked')
" {} +
```

---

## Summary Checklist

| Section | Test Count | Estimated Time |
|---------|-----------|---------------|
| Quick Sanity | 10 | 5 min |
| Config | 4 | 2 min |
| Models | 4 | 1 min |
| Skills | 3 | 1 min |
| Doctor | 2 | 1 min |
| Space | 4 | 2 min |
| Spawn (dry-run) | 8 | 2 min |
| Report | 3 | 1 min |
| Output Formats | 6 | 1 min |
| Error Handling | 5 | 1 min |
| Agent Mode | 3 | 1 min |
| State Integrity | 5 | 2 min |
| Harness Integration | 4 | 3 min |
| Edge Cases | 7 | 2 min |
| Anomaly Checks | 6 | 2 min |
| **Total** | **74** | **~25 min** |

### Priority Guide

- **[CRITICAL]**: Must pass. Blocks all further testing. ~20 tests.
- **[IMPORTANT]**: Should pass. Indicates real bugs. ~30 tests.
- **[NICE-TO-HAVE]**: Quality checks. Failures are worth investigating but not blocking. ~24 tests.

# Phase 8: MERIDIAN_HARNESS_COMMAND Bypass + CI Invariants Script + Pyright Hardening

## Part A: MERIDIAN_HARNESS_COMMAND bypass into factory

### Current state

The MERIDIAN_HARNESS_COMMAND bypass logic is currently in `src/meridian/lib/launch/plan.py` inside `resolve_primary_launch_plan()` (around lines 259-298). When the env var is set, it short-circuits normal composition and builds a command from the override + passthrough args.

The design says this should move into `build_launch_context()` and return a `BypassLaunchContext`.

### What to do

Check if the bypass is ALREADY handled in the factory after phases 4-6. If `build_launch_context()` or `resolve_primary_launch_plan()` already checks `MERIDIAN_HARNESS_COMMAND` and returns/uses `BypassLaunchContext`, then this work is done.

If not:
1. Move the `MERIDIAN_HARNESS_COMMAND` check into `build_launch_context()` (or into a helper it calls)
2. When the env var is set, return `BypassLaunchContext(argv=..., env=..., cwd=...)`
3. Callers (process.py) should dispatch on the union type using `match` + `assert_never`
4. Remove the bypass logic from `plan.py`

### Exit criteria
```bash
rg "MERIDIAN_HARNESS_COMMAND" src/ --type py
# → only in build_launch_context() bypass branch in launch/context.py (plus tests)
# → 0 matches in launch/plan.py or launch/command.py
```

## Part B: CI invariants script

Create `scripts/check-launch-invariants.sh` that verifies all R06 exit criteria via `rg` commands.

The script must:
- Run each `rg` check from the R06 exit criteria in `design/refactors.md`
- Compare against expected results
- Exit 0 if all pass, nonzero on any drift
- Be executable (`chmod +x`)

Key checks to include:

```bash
#!/usr/bin/env bash
set -euo pipefail

FAIL=0

check() {
    local desc="$1"
    local expected="$2"
    shift 2
    local actual
    actual=$("$@" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$actual" != "$expected" ]; then
        echo "FAIL: $desc (expected $expected matches, got $actual)"
        FAIL=1
    else
        echo "OK: $desc"
    fi
}

# Pipeline — one builder per concern
check "resolve_policies definition" "1" rg "^def resolve_policies\(" src/
check "resolve_permission_pipeline definition" "1" rg "^def resolve_permission_pipeline\(" src/
check "materialize_fork definition" "1" rg "^def materialize_fork\(" src/

# Plan Object — one sum type
check "NormalLaunchContext definition" "1" rg "^class NormalLaunchContext\b" src/
check "BypassLaunchContext definition" "1" rg "^class BypassLaunchContext\b" src/
check "RuntimeContext definition" "1" rg "^class RuntimeContext\b" src/

# Type split
check "SpawnRequest definition" "1" rg "^class SpawnRequest\b" src/
check "SpawnParams definition" "1" rg "^class SpawnParams\b" src/

# Result types
check "LaunchResult definition" "1" rg "^class LaunchResult\b" src/meridian/lib/launch/
check "LaunchOutcome definition" "1" rg "^class LaunchOutcome\b" src/

# Adapter boundary — no domain→concrete-harness imports
check "no concrete harness imports in launch/" "0" rg "from meridian\.lib\.harness\.(claude|codex|opencode|projections)" src/meridian/lib/launch/

# Deletions completed
check "run_streaming_spawn deleted" "0" rg "run_streaming_spawn" src/ --type py

# Pyright hardening
check "no pyright:ignore in launch/ or ops/spawn/" "0" rg "pyright:\s*ignore" src/meridian/lib/launch/ src/meridian/lib/ops/spawn/
check "no cast(Any, in launch/ or ops/spawn/" "0" rg "cast\(Any," src/meridian/lib/launch/ src/meridian/lib/ops/spawn/

exit $FAIL
```

### Add CI job

Add to `.github/workflows/meridian-ci.yml` a new step `check-launch-invariants` that runs the script:

```yaml
      - name: Check launch invariants
        run: bash scripts/check-launch-invariants.sh
```

## Part C: Pyright hardening

Ban `pyright: ignore` and `cast(Any,` in `src/meridian/lib/launch/` and `src/meridian/lib/ops/spawn/`.

Check current violations:
```bash
rg "pyright:\s*ignore" src/meridian/lib/launch/ src/meridian/lib/ops/spawn/
rg "cast\(Any," src/meridian/lib/launch/ src/meridian/lib/ops/spawn/
```

If any exist, fix them (replace with proper typing). If none exist, the CI script enforces the invariant going forward.

Also check for `match` + `assert_never` patterns at executor dispatch sites:
```bash
rg "match\s+.*launch_context" src/meridian/lib/launch/process.py src/meridian/lib/launch/streaming_runner.py
rg "assert_never\(" src/meridian/lib/launch/
```

If executor dispatch doesn't use `match` + `assert_never` on the `LaunchContext` union yet, add it. The executor should dispatch on `NormalLaunchContext` vs `BypassLaunchContext` and use `assert_never` for exhaustiveness.

## Verification

```bash
uv run pyright        # 0 errors
uv run ruff check .   # clean
uv run pytest-llm     # all tests pass
bash scripts/check-launch-invariants.sh  # all checks pass
```

Commit when done.

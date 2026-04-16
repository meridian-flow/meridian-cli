#!/usr/bin/env bash
# R06 launch invariants — heuristic drift guardrails.
# Runs on CI to catch named-call-pattern drift. See design/refactors.md R06 exit criteria.
set -euo pipefail

FAIL=0

# Prefer rg if available, fall back to grep -rP
if command -v rg &>/dev/null; then
    SEARCH="rg"
else
    SEARCH="grep_compat"
fi

# Wrapper that mimics rg behavior using grep -rP
grep_compat() {
    local pattern="$1"; shift
    local args=()
    local type_filter=""
    while [ $# -gt 0 ]; do
        case "$1" in
            --type)
                type_filter="$2"; shift 2;;
            *)
                args+=("$1"); shift;;
        esac
    done
    local grep_args=(-rP "$pattern")
    if [ -n "$type_filter" ]; then
        grep_args+=(--include="*.$type_filter")
    fi
    grep "${grep_args[@]}" "${args[@]}" || true
}

search() {
    if [ "$SEARCH" = "rg" ]; then
        rg "$@" || true
    else
        grep_compat "$@"
    fi
}

check() {
    local desc="$1"
    local expected="$2"
    shift 2
    local actual
    actual=$(search "$@" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$actual" != "$expected" ]; then
        echo "FAIL: $desc (expected $expected matches, got $actual)"
        FAIL=1
    else
        echo "OK: $desc"
    fi
}

check_at_least() {
    local desc="$1"
    local minimum="$2"
    shift 2
    local actual
    actual=$(search "$@" 2>/dev/null | wc -l | tr -d ' ')
    if [ "$actual" -lt "$minimum" ]; then
        echo "FAIL: $desc (expected at least $minimum matches, got $actual)"
        FAIL=1
    else
        echo "OK: $desc"
    fi
}

# Pipeline — one builder per concern
check "resolve_policies definition" "1" "^def resolve_policies\(" src/
check "resolve_permission_pipeline definition" "1" "^def resolve_permission_pipeline\(" src/
check "materialize_fork definition" "1" "^def materialize_fork\(" src/

# Plan Object — one sum type
check "NormalLaunchContext definition" "1" "^class NormalLaunchContext\b" src/
check "BypassLaunchContext definition" "1" "^class BypassLaunchContext\b" src/
check "RuntimeContext definition" "1" "^class RuntimeContext\b" src/

# Executor dispatch exhaustiveness + hardening
check "match dispatch on launch_context in executors" "2" "match\s+.*launch_context" src/meridian/lib/launch/process.py src/meridian/lib/launch/streaming_runner.py
check_at_least "assert_never use in launch dispatch" "2" "assert_never\(" src/meridian/lib/launch/
check "no pyright:ignore in launch/ or ops/spawn/" "0" "pyright:\s*ignore" src/meridian/lib/launch/ src/meridian/lib/ops/spawn/
check "no cast(Any, in launch/ or ops/spawn/" "0" "cast\(Any," src/meridian/lib/launch/ src/meridian/lib/ops/spawn/

# Type split
check "SpawnRequest definition" "1" "^class SpawnRequest\b" src/
check "SpawnParams definition" "1" "^class SpawnParams\b" src/

# Result types
check "LaunchResult definition" "1" "^class LaunchResult\b" src/meridian/lib/launch/context.py
check "LaunchOutcome definition" "1" "^class LaunchOutcome\b" src/meridian/lib/launch/context.py

# Adapter boundary — no domain→concrete-harness imports
check "no concrete harness imports in launch/" "0" "from meridian\.lib\.harness\.(claude|codex|opencode|projections)" src/meridian/lib/launch/

# Bypass ownership
check_at_least "MERIDIAN_HARNESS_COMMAND in context factory" "1" "MERIDIAN_HARNESS_COMMAND" src/meridian/lib/launch/context.py
check "no MERIDIAN_HARNESS_COMMAND in plan.py" "0" "MERIDIAN_HARNESS_COMMAND" src/meridian/lib/launch/plan.py
check "no MERIDIAN_HARNESS_COMMAND in command.py" "0" "MERIDIAN_HARNESS_COMMAND" src/meridian/lib/launch/command.py

# Deletions completed
check "run_streaming_spawn deleted" "0" "run_streaming_spawn" src/ --type py

exit "$FAIL"

# Observability Requirements

GitHub issue: #38

## Problem

Two related gaps:

1. **Crash diagnostics** — Runner process crashes leave no trace. The reaper detects dead processes but we can't diagnose why they died.

2. **Log noise** — Warnings and debug info pollute spawn stderr, which parents parse for results. Only critical errors should hit terminal; everything else should route to files.

## Requirements

### Crash Diagnostics

1. **Per-spawn runner log** — persist runner logs to `.meridian/spawns/pXXXX/runner.log`
2. **Unhandled exception capture** — log exceptions that escape the async main loop before exit
3. **Signal tracing** — log signal reception (SIGTERM, SIGINT, etc.) with timestamps
4. **Crash sentinel** — write crash reason to a file so reaper can report richer failure info
5. **CLI surfacing** — `meridian spawn show` displays crash reason when available

### Log Discipline

1. **Stderr is for critical errors only** — warnings, debug info, and "FYI" messages go to files
2. **Per-spawn log capture** — warnings during spawn execution route to spawn artifact directory
3. **Harness projection noise** — capability mismatch warnings (e.g., unsupported flags) are silent or DEBUG level

## Constraints

- Existing tests must pass
- Log format should be structured (JSON lines or similar) for parseability
- Must not significantly impact spawn startup latency

## Done

- [x] Remove Codex tool-flag warnings (1f4bc46) — silent drop, no user action possible

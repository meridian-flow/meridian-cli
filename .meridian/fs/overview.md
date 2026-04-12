# Meridian — System Overview

Meridian is a harness-agnostic multi-agent coordination CLI. It launches, tracks, and supervises AI agent processes (spawns) across multiple harness backends. It is not an execution engine or data warehouse — it is a coordination layer.

## Major Subsystems

```
src/meridian/
  cli/            CLI entry point (cyclopts), command groups, registration
  server/         MCP stdio server (FastMCP)
  lib/
    ops/          Operation manifest — shared API surface for CLI and MCP
    harness/      Subprocess adapters: Claude, Codex, OpenCode, Direct
    state/        JSONL event stores (spawns, sessions), mutable JSON (work items)
    catalog/      Model resolution, agent/skill loading, default agent policy
    launch/       Spawn lifecycle: prepare → resolve → process → finalize
    config/       Settings model, precedence chain, TOML read/write
    core/         Shared utilities (overrides, signals, codec, logging)
  dev/            Token-efficient pytest wrapper
```

## How Subsystems Connect

**Entry points → ops → lib:**
- `meridian spawn ...` (CLI) and `spawn_create` (MCP tool) both call `spawn_create_sync` from `ops/spawn/api.py`
- All user-facing operations are declared in `ops/manifest.py` as `OperationSpec` instances
- CLI commands are auto-generated or explicitly registered from the manifest; the MCP server registers the same ops as FastMCP tools
- See `fs/ops/overview.md` for the manifest architecture

**Launch flow:**
1. `ops/spawn/prepare.py` — validates input, resolves model aliases (via catalog), loads agent profile and skills, renders reference files and prior context, computes permission policy
2. `lib/launch/resolve.py` — two-pass policy resolution: agent profile selection influences the final model/harness/safety layers
3. `lib/launch/process.py` — creates session, starts spawn as queued (recording runner_pid), attaches to work item, calls runner
4. `lib/launch/runner.py` — `spawn_and_stream()`: subprocess execution, stdout/stderr capture, report watchdog, stdin feeding, exit code mapping; writes exited event immediately after process exits
5. `lib/launch/extract.py` + `report.py` — extract usage/session/report from harness output, persist report artifact

**State flow:**
- Every spawn is append-only JSONL events in `.meridian/spawns.jsonl`
- Session state is JSONL events in `.meridian/sessions.jsonl`
- Work items are mutable JSON under `.meridian/work-items/`
- All writes are atomic (tmp+rename) with `fcntl.flock` for concurrency
- Crash recovery: the reaper (`lib/state/reaper.py`) detects orphaned spawns on read paths — psutil liveness checks on `runner_pid` (`lib/state/liveness.py:is_process_alive()`), `exited_at` event presence, durable report completion — no explicit recovery step

**Mars integration:**
- `meridian mars ...` is a passthrough to the bundled `mars` binary
- Mars manages `.agents/` (agent profiles, skill content) from package sources
- Model alias resolution calls `mars models list --json` at resolve time
- See `fs/mars/overview.md`

## Key Design Decisions

**Files-as-authority:** All state lives under `.meridian/`. No database, no hidden state. `cat .meridian/spawns.jsonl | jq` reveals everything. This makes the system inspectable, backup-friendly, and testable without service dependencies.

**Crash-only design:** No graceful shutdown path. Atomic writes (tmp+rename) mean every write either completes or leaves the prior state intact. JSONL readers skip truncated/malformed lines. The reaper runs on read paths, not a background daemon — `meridian status` is the recovery trigger.

**Harness-agnostic:** Meridian never assumes a specific AI harness. The adapter contract (`lib/harness/adapter.py:HarnessCapabilities`) declares what each harness supports (stream events, session resume, native skills, etc.). Command construction, output parsing, and session detection are adapter-private. Adding a harness = one adapter file + registry entry.

**Manifest as single source of truth:** `ops/manifest.py` declares every operation once with name, description, input/output types, async+sync handlers, and surface membership (CLI and/or MCP). Both the CLI registration layer and the MCP server consume the manifest — no duplicated operation definitions.

**Config precedence:** CLI flags > ENV vars > agent profile > project config > user config > harness defaults. Each field resolves independently — a CLI model override forces harness re-derivation from the overridden model, not from the profile's harness.

## State Root Layout

```
.meridian/
  spawns.jsonl          append-only spawn events
  sessions.jsonl        append-only session events
  session-id-counter    monotonic counter for c1, c2, ...
  config.toml           project config overrides
  fs/                   agent-facing codebase mirror (this directory)
  work/                 active work scratch dirs
  work-archive/         archived work scratch dirs
  work-items/           mutable JSON per work item
  spawns/               per-spawn artifact dirs (<id>/prompt.md, report.md, ...)
  artifacts/            artifact blob store for spawn outputs (LocalStore)
  cache/                models.json cache, other transient data
```

## Surface Summary

| Surface | Entry point | Transport |
|---------|-------------|-----------|
| CLI | `meridian` (cyclopts) | stdio, human-readable |
| MCP | `meridian serve` (FastMCP) | stdio, JSON-RPC |
| Direct | `DirectAdapter` in-process | Python API, no subprocess |

The MCP surface exposes a subset of operations suited for programmatic agent use. Config operations and session/work management are CLI-only. Spawn create/continue are MCP-only (the CLI's bare `meridian spawn` is the default action, not a registered subcommand).

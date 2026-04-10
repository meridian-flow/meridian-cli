# Streaming Parity — Design Overview (v2)

## Entry Point

This work item aligns subprocess and streaming harness launch behavior around typed launch specs, shared projection modules, and explicit permission enforcement.

Read order:

1. [overview.md](overview.md)
2. [typed-harness.md](typed-harness.md)
3. [launch-spec.md](launch-spec.md)
4. [transport-projections.md](transport-projections.md)
5. [permission-pipeline.md](permission-pipeline.md)
6. [runner-shared-core.md](runner-shared-core.md)
7. [edge-cases.md](edge-cases.md)

## Problem

v1 introduced `ResolvedLaunchSpec` but left load-bearing enforcement optional:

- fallback spec construction (`ResolvedLaunchSpec(...)`) could bypass harness-specific behavior
- `PermissionResolver` was nullable in practice
- streaming Codex ignored sandbox/approval intent
- projection completeness guarantees were incomplete and per-module drift prone
- shared runner logic still had harness-specific branching

## Solution Shape

### 1. Typed harness boundaries

- Shared leaf types in `src/meridian/lib/launch/launch_types.py`
- Generic adapter/connection contracts in `src/meridian/lib/harness/adapter.py` and `connections/base.py`
- Runtime dispatch guard in `SpawnManager.start_spawn`

### 2. Mandatory spec factories

- No base fallback for `resolve_launch_spec`
- Base validator on `ResolvedLaunchSpec` enforces `continue_fork` requires `continue_session_id`

### 3. Projection modules with guard helper

Projection module layout:

- `projections/_guards.py`
- `projections/project_claude.py`
- `projections/project_codex_subprocess.py`
- `projections/project_codex_streaming.py`
- `projections/project_opencode_subprocess.py`
- `projections/project_opencode_streaming.py`

Each module runs `_check_projection_drift(...)` at import time.

### 4. Permission pipeline is strict by default

- `PermissionResolver` non-optional
- `PermissionConfig.approval` literal-typed
- REST server rejects missing permission metadata by default (`HTTP 400`)
- opt-out only via `--allow-unsafe-no-permissions` using `UnsafeNoOpPermissionResolver`

### 5. Shared launch context with adapter-owned preflight

- `src/meridian/lib/launch/context.py` owns `prepare_launch_context(...)`
- shared runner constants in `src/meridian/lib/launch/constants.py`
- shared launch text helpers in `src/meridian/lib/launch/text_utils.py`
- typed harness registry in `src/meridian/lib/harness/bundle.py`
- Claude-specific preflight in `src/meridian/lib/harness/claude_preflight.py` via `adapter.preflight(...)`
- no `if harness_id == ...` branches in shared launch context

Import topology (including `_guards.py`, `_reserved_flags.py`, `bundle.py`, `context.py`, `constants.py`, and `text_utils.py`) is authoritative in [typed-harness.md §Import Topology](typed-harness.md#import-topology) and is the verification source for E31/S031.

## Policy Clarifications

- Codex sandbox/approval are projected from `spec.permission_resolver.config` (not stored on `CodexLaunchSpec`).
- `--append-system-prompt` collision policy: Meridian-managed flag appears first, user passthrough copy remains later; user value wins by last-wins semantics; warning log emitted.
- Reserved permission flags in passthrough args are stripped (or merged for Claude permission flags) with warning logs.
- Codex fail-closed rule applies if requested permission semantics cannot be expressed by `codex app-server`.

## Scope

In scope:

- p1411 HIGH/MEDIUM closure
- typed dispatch guard + projection guard helper
- transport-wide field accounting for streaming paths
- strict permission defaults + explicit unsafe opt-out
- projection module renaming and Codex streaming projection merge

Out of scope:

- full runner decomposition (tracked by D19 budget/trigger)
- MCP wiring (stubbed out for v2)
- new harnesses

## Success Criteria

- new spec/spawn field drift fails at import-time or type-check time
- no silent permission fallbacks
- subprocess and streaming projections remain semantically aligned
- no shared-core harness-id branching
- scenario suite S001–S038 covers edge cases and enforcement boundaries

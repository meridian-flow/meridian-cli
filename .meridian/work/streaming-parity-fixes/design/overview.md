# Streaming Parity — Design Overview (v2, revision round 3)

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

## Guiding Principle — Coordinator, Not Policy Engine

Meridian is a coordination layer. It launches harnesses, forwards configuration, captures events, manages spawn lifecycle, and persists state. It does **not** execute tool calls, enforce sandboxes, validate what harnesses decide is allowed, or second-guess what users pass through.

Every strict check in v2 must answer the question: *does this protect against meridian's own internal drift?* If the answer is "no — it's policing user or harness behavior", the check does not belong here.

- **Strict** for developer drift (spec/projection accounting, dispatch typing, bundle registration, import topology).
- **Forgiving** for user/harness data (`extra_args` is verbatim passthrough; permission combinations the harness accepts, meridian accepts).

The revision round 3 edits delete the overreach (reserved-flag stripping, combination validators, MCP prefix guards) and codify the missing internal-consistency invariants (K1–K9 in `decisions.md`).

## Problem

v1 introduced `ResolvedLaunchSpec` but left load-bearing enforcement optional:

- fallback spec construction (`ResolvedLaunchSpec(...)`) could bypass harness-specific behavior
- `PermissionResolver` was nullable in practice
- streaming Codex ignored sandbox/approval intent
- projection completeness guarantees were incomplete and per-module drift prone
- shared runner logic still had harness-specific branching

v2 rounds 1–2 closed those gaps but introduced overreach (reserved-flag stripping, `mcp_` prefix guards, deletion of `mcp_tools`, and a resolver signature that invited harness-id branching inside the resolver). Round 3 reframes the boundary and codifies the invariants that audits p1433 / p1434 / p1435 identified as genuinely load-bearing.

## Solution Shape

### 1. Typed harness boundaries

- Shared leaf types in `src/meridian/lib/launch/launch_types.py`
- Generic adapter / connection / extractor contracts in `src/meridian/lib/harness/adapter.py`, `connections/base.py`, `extractors/base.py`
- Runtime dispatch guard in `SpawnManager.start_spawn`, keyed on `(harness_id, transport_id)`
- Bundle registration via a single `register_harness_bundle(...)` helper that raises on duplicates (K2)
- `BaseHarnessAdapter.id` is abstract so Protocol/ABC method sets stay reconciled (K3)

### 2. Mandatory spec factories with per-adapter field accounting

- No base fallback for `resolve_launch_spec`
- Base validator on `ResolvedLaunchSpec` enforces `continue_fork` requires `continue_session_id`
- Each adapter exposes a `handled_fields: frozenset[str]` that must union to `SpawnParams.model_fields` at import time (K9)
- `mcp_tools` is a first-class forwarded field (reversing round 2's D23) so manual MCP configuration still flows through (D4)

### 3. Projection modules with guard helper

Projection module layout:

- `projections/_guards.py`
- `projections/project_claude.py`
- `projections/project_codex_subprocess.py`
- `projections/project_codex_streaming.py`
- `projections/project_opencode_subprocess.py`
- `projections/project_opencode_streaming.py`

Each module runs `_check_projection_drift(...)` at import time. `harness/__init__.py` imports every projection module eagerly so the guards always execute (C2).

There is no `projections/_reserved_flags.py`. Reserved-flag stripping is deleted (D1). `extra_args` is forwarded verbatim to each transport.

### 4. Permission pipeline is strict for meridian-owned invariants, forgiving for user intent

- `PermissionResolver` is non-optional.
- `PermissionConfig` is immutable (`model_config = ConfigDict(frozen=True)`) to protect meridian's own internal state (K7). It does **not** validate which combinations "look right" (D2).
- `PermissionResolver.resolve_flags(...)` no longer takes a `harness` parameter — projections read abstract intent from `PermissionConfig` and translate to wire format per harness (K4).
- REST server rejects missing permission metadata by default (`HTTP 400`); opt-out only via `--allow-unsafe-no-permissions` using `UnsafeNoOpPermissionResolver`.
- `PermissionConfig` Literals are retained but explicitly marked as "known values, extensible at source without API break" — adding a new sandbox tier or approval mode is a one-line edit and does not gate on network validation (D5).

### 5. Shared launch context with adapter-owned preflight

- `src/meridian/lib/launch/context.py` owns `prepare_launch_context(...)`
- shared runner constants in `src/meridian/lib/launch/constants.py`
- shared launch text helpers in `src/meridian/lib/launch/text_utils.py`
- typed harness registry in `src/meridian/lib/harness/bundle.py`
- Claude-specific preflight in `src/meridian/lib/harness/claude_preflight.py` via `adapter.preflight(...)`
- `RuntimeContext.child_context()` is the sole producer of `MERIDIAN_*` runtime overrides (K5), restricted to a whitelisted set (`MERIDIAN_REPO_ROOT`, `MERIDIAN_STATE_ROOT`, `MERIDIAN_DEPTH`, `MERIDIAN_CHAT_ID`, `MERIDIAN_FS_DIR`, `MERIDIAN_WORK_DIR`). Neither `plan.env_overrides` nor `preflight.extra_env` may contain any `MERIDIAN_*` key; `merge_env_overrides` scans both and raises on leaks.
- no `if harness_id == ...` branches in shared launch context

Import topology (including `_guards.py`, `bundle.py`, `context.py`, `constants.py`, and `text_utils.py`) is authoritative in [typed-harness.md §Import Topology](typed-harness.md#import-topology) and is the verification source for E31/S031.

### 6. Transport dispatch keyed on `(harness_id, transport_id)`

`HarnessBundle[SpecT]` carries a `connections` mapping from `TransportId` to connection classes (K1), plus a `HarnessExtractor[SpecT]` so session-id detection and report extraction stay symmetric across subprocess and streaming transports (K6).

## Policy Clarifications

- Codex sandbox/approval are projected from `spec.permission_resolver.config` (not stored on `CodexLaunchSpec`).
- `--append-system-prompt` collision policy: Meridian-managed flag appears first, user passthrough copy remains later; user value wins by last-wins semantics; warning log emitted so users can see meridian is also emitting the flag.
- `extra_args` is forwarded verbatim. If a user passes `-c sandbox_mode=yolo` or `--allowedTools X`, that goes through to the harness exactly as written. Permission intent is normally expressed via `PermissionConfig`; users taking manual control via `extra_args` is a supported escape hatch, not a security boundary.
- Codex fail-closed rule still applies when requested `PermissionConfig` semantics cannot be expressed by `codex app-server` — this protects meridian from silently downgrading the **user-requested intent**, not from the user deliberately overriding intent via passthrough.
- `mcp_tools` is forwarded through the launch spec to each projection. Auto-packaging MCP through mars remains out of scope for v2; manual MCP configuration via `SpawnParams.mcp_tools` works today.

## Scope

In scope:

- p1411 HIGH/MEDIUM closure
- typed dispatch guard + projection guard helper + per-adapter field accounting (K9)
- transport-wide field accounting for streaming paths
- strict permission defaults + explicit unsafe opt-out
- projection module renaming and Codex streaming projection merge
- bundle registry uniqueness (K2), Protocol/ABC reconciliation (K3), `(harness, transport)` dispatch (K1)
- cancel/interrupt parity semantics (K8)
- spec and config immutability coverage (K7)
- session ID extraction parity via `HarnessExtractor` (K6) — **pulled in to v2**; fallback detection from harness-specific artifacts (Claude project files, Codex rollout files, OpenCode logs) is symmetric across subprocess and streaming
- `MERIDIAN_*` runtime override sole-producer invariant (K5)
- `mcp_tools` restored as first-class forwarded field (D4)

Out of scope:

- full runner decomposition (tracked by D19 budget/trigger)
- MCP auto-packaging through mars (manual `mcp_tools` works in v2)
- new harnesses
- policing user-supplied `extra_args` content or combinations of `PermissionConfig` values

## Success Criteria

- new spec/spawn field drift fails at import-time or type-check time
- new `SpawnParams` field without an adapter owner fails at import time (K9)
- duplicate harness bundle registration fails at import time (K2)
- no silent permission fallbacks
- subprocess and streaming projections remain semantically aligned
- subprocess and streaming share session-id detection and report extraction via `HarnessExtractor` (K6)
- no shared-core harness-id branching; no resolver-side harness-id branching (K4)
- `extra_args` reaches the harness verbatim for every supported harness
- `PermissionConfig` and `ResolvedLaunchSpec` instances cannot be mutated after construction (K7)
- cancel and interrupt are idempotent and converge to a single terminal status (K8)
- scenario suite (S001–S0xx, extended in revision 3) covers edge cases and enforcement boundaries

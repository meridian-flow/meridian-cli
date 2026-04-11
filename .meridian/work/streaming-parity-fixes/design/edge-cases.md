# Edge Cases, Failure Modes, Boundary Conditions

## Purpose

Authoritative edge-case set for v2. Each item maps to `scenarios/Sxxx-*.md` and must be verified before completion.

Revision round 3 retires E37 (reserved-flag stripping) and adds E39–E46 covering the new meridian-internal invariants (K1–K9). Every check here protects meridian from its own drift; nothing here polices user or harness data.

## Category A — Type and Contract Boundaries

### E1 — Adapter omits `resolve_launch_spec`

Expected: pyright structural failure + runtime `TypeError` from ABC abstract-method enforcement (`BaseHarnessAdapter`), not from Protocol instantiation.

### E2 — Base spec passed to concrete connection

Expected: pyright type error and runtime `TypeError` at dispatch boundary (`isinstance(spec, bundle.spec_cls)` guard in `SpawnManager.start_spawn`), not in per-connection behavior-switching branches.

### E3 — `None` permission resolver

Expected: type error; no cast-to-None path.

### E4 — Resolver lacks `.config`

Expected: Protocol conformance/type-check failure.

### E5 — New `ClaudeLaunchSpec` field missed by projection

Expected: import-time `ImportError` via `_check_projection_drift`.

### E6 — New `SpawnParams` field missed by factory accounting

Expected: import-time `ImportError` from `_enforce_spawn_params_accounting()` — the per-adapter union over every registered bundle's `handled_fields` fails to cover the new field. The legacy module-level `_SPEC_HANDLED_FIELDS` is now derived from `SpawnParams.model_fields` and used only for error formatting; the authoritative check is the per-adapter union guard.

### E40 — Protocol/ABC method-set reconciliation (K3)

A subclass of `BaseHarnessAdapter` that forgets to declare `id` is currently ABC-instantiable (because `id` wasn't abstract on the base) but Protocol-noncompliant, and crashes deep in dispatch with `AttributeError`. Expected after K3: `id` is `@abstractmethod` on the base, so missing `id` fails at instantiation with `TypeError`. A unit test reconciles the Protocol attribute set against the ABC abstract-method set and fails if they diverge.

### E42 — New `SpawnParams` field present globally but unclaimed by any adapter (K9)

A developer adds a new `SpawnParams` field but forgets to add it to any adapter's `handled_fields`. Expected: import-time `ImportError` from the per-adapter union check in `_enforce_spawn_params_accounting(registry=None)` at the tail of `harness/__init__.py`. The error reports the missing field alongside the per-adapter `handled_fields` map for debuggability (K9 enforces `handled_fields = consumed_fields | explicitly_ignored_fields` so a deliberate ignore is still a claim).

## Category B — Permission Flow

### E7 — Streaming Codex with `sandbox=read-only`

Expected: app-server launch projects read-only sandbox semantics; write attempts rejected by Codex.

### E8 — Streaming Codex with `approval=auto`

Expected: semantic auto-accept behavior and audit trace.

### E9 — Streaming Codex with `approval=default`

Expected: no forced override; harness default preserved.

### E10 — Streaming Codex with `approval=confirm`

Expected: rejection event enqueued before `send_error` is awaited.

### E11 — Streaming Claude `--allowedTools` resolver-internal dedupe

Expected: the Claude resolver deduplicates its own multi-source output (parent-forwarded + explicit + profile-defaults) into one `--allowedTools` emission. Dedupe is internal to the resolver/projection and does NOT touch user `extra_args`.

### E12 — Subprocess Claude parity with E11

Expected: same deduped semantics in the resolver output, identical projection for the same `spec`.

### E13 — REST `/spawns` missing permission metadata

Expected: strict default rejects request (`HTTP 400`). Only if `--allow-unsafe-no-permissions` is enabled may `UnsafeNoOpPermissionResolver` be used.

### E14 — `run_streaming_spawn` caller-provided resolver

Expected: caller resolver flows through unchanged.

### E43 — `PermissionConfig` is frozen (K7)

Expected: attempting to mutate `config.sandbox = "yolo"` after construction raises `ValidationError` / `TypeError` (Pydantic's frozen model semantics). Guards meridian-internal state against accidental mutation during merge or projection.

## Category C — Spec-to-Wire Completeness and Projection Semantics

### E15 — Claude full-field round-trip

Expected: canonical order and field-by-field wire mapping table coverage, including `mcp_tools`.

### E16 — Codex sandbox x approval matrix

Expected: distinct semantic behavior + audit trail per cell. Wire strings may collapse where harness supports fewer distinct knobs.

### E17 — OpenCode model prefix normalization

Expected: one-time normalization.

### E18 — OpenCode skills single-injection

Expected: exactly one authoritative skills channel.

### E19 — Codex `report_output_path`

Expected: subprocess emits `-o`; streaming ignores wire emission and logs debug note.

### E20 — `continue_fork=True` without session ID

Expected: base-spec validator failure for all harness subclasses.

### E47 — `mcp_tools` projected on every harness (D4)

Expected: `mcp_tools = ("tool1", "tool2")` reaches the Claude `--mcp-config` flags, the Codex `-c mcp.servers.*.command=...` arguments, and the OpenCode session payload `mcp` field. Empty `mcp_tools` produces no wire-level MCP state on any harness.

## Category D — Arg Ordering and Override Policy

### E21 — Claude subprocess/streaming arg-tail parity

Expected: same projected tail for same spec, including verbatim `extra_args`.

### E22 — User `--append-system-prompt` in passthrough

Expected: both flags appear in output (Meridian-managed copy in canonical position, user copy in the verbatim `extra_args` tail). User wins by last-wins semantics. Debug log notes the collision.

### E23 — `--allowedTools` from resolver + user passthrough

Expected: resolver-derived `--allowedTools` appears in canonical position; user's `extra_args` copy appears verbatim in the tail. Both are forwarded to Claude. Claude's own flag-handling decides the effective behavior. Meridian does not merge or strip (D1).

## Category E — Shared Core and Structure

### E24 — `LaunchContext` parity (narrowed — C1)

Expected: for identical inputs, the deterministic subset of `LaunchContext` is equal across callers: `run_params`, `spec`, `child_cwd`, `env_overrides`. The `env` field as a whole depends on ambient `os.environ` and is NOT in the parity contract.

### E25 — Parent Claude permissions forwarding

Expected: identical preflight semantics across runners via adapter preflight.

### E26 — Shared constants only

Expected: no duplicate constants in runner files.

### E44 — `preflight.extra_env` attempts to set a `MERIDIAN_*` key (K5)

Expected: `merge_env_overrides(...)` raises `RuntimeError` at launch time. `RuntimeContext.child_context()` is the sole producer of `MERIDIAN_*` overrides.

## Category F — Environment and Runtime Failures

### E27 — `python -O` behavior

Expected: guard behavior unchanged (no assert-based enforcement).

### E28 — Missing harness binary

Expected: shared structured `HarnessBinaryNotFound` error semantics across runners.

### E29 — Invalid Codex passthrough args

Expected: debug log before launch and clean surfaced failure. Meridian forwards verbatim; Codex decides what to do with the flag.

## Category G — Import Order / Guard Coverage

### E30 — Projection guard import-time behavior

Expected: `project_*` modules fail at import on drift. Eager imports in `harness/__init__.py` guarantee all guards execute at package load.

### E31 — No circular imports

Expected: DAG centered on `launch_types.py` remains acyclic.

### E36 — Delegated field has no consumer

Expected: transport-wide accounted-field union check fails import when any delegated field is unconsumed.

### E39 — Duplicate `register_harness_bundle(...)` (K2)

Expected: second call with the same `harness_id` raises `ValueError`. Catches double-import scenarios or two modules claiming the same harness id.

### E45 — `(harness, transport)` dispatch for an unsupported transport (K1)

Expected: `get_connection_cls(harness, transport)` raises `KeyError` with a clear message. Dispatch guard does not crash silently or fall back to an unintended connection class.

## Category H — Observability

### E32 — Confirm-mode rejection event ordering

Expected: enqueue-before-send ordering assertion uses call sequence/sequence id, not wall-clock.

### E33 — Passthrough debug log on streaming

Expected: Codex debug log in `project_codex_spec_to_appserver_command`; OpenCode debug log in `project_opencode_spec_to_serve_command`. Both log the verbatim `extra_args` list.

### E38 — Codex fail-closed capability mismatch

Expected: if requested `PermissionConfig` semantics cannot be represented by app-server interface, raise `HarnessCapabilityMismatch` and fail spawn before launch. Protects meridian-internal promise vs capability; NOT a policy on user `extra_args`.

### E48 — `extra_args` forwarded verbatim (D1, replaces E37)

Expected: user `extra_args` containing `-c sandbox_mode=yolo`, `--dangerous-flag`, or `--allowedTools C,D` flow to the harness command line unmodified. No stripping, no rewriting, no warning-and-drop. Debug log records the verbatim contents.

## Category I — Connection Surface and Lifecycle

### E34 — `OpenCodeConnection` inherits `HarnessConnection`

Expected: inheritance enforced.

### E35 — Unified connection interface

Expected: all concrete connections satisfy same `HarnessConnection` ABC surface.

### E41 — Cancel / interrupt / SIGTERM parity (K8)

Expected:

- `send_cancel()` is idempotent; repeat calls after the first collapse to a no-op and produce exactly one `cancelled` terminal spawn status.
- `send_interrupt()` is idempotent with the same semantics.
- Runner-level SIGTERM/SIGINT translates to exactly one `send_cancel()` invocation per active connection.
- Cancellation event emission is exactly-once and ordered before any subsequent error emission on the same connection.
- Semantics are the same across subprocess and streaming connections.

## Category J — Session ID Extraction and Artifact Parity (new in round 3)

### E46 — Streaming session id detection via extractor fallback (K6)

Expected: when the streaming event frame does not carry a session id, `bundle.extractor.detect_session_id_from_artifacts(...)` scans harness-specific artifacts (Claude project files, Codex rollout files, OpenCode logs) using the same code path as subprocess. Subprocess and streaming reach the same session id from the same artifact set.

### E49 — Missing extractor in bundle

Expected: `HarnessBundle(..., extractor=None)` is rejected at registration (type-check or explicit non-None validation in `register_harness_bundle`). No runtime `AttributeError` when a runner reaches for `bundle.extractor`.

# Decisions — Streaming Parity Fixes (v2)

## D1 — Generic binding with runtime-checked dispatch narrow

**Decision.** Use `SpecT`-bound generic adapters/connections and a single dispatch-site runtime guard:

- `if not isinstance(spec, bundle.spec_cls): raise TypeError(...)`
- then `cast(SpecT, spec)` for `connection.start(...)`

**Why.** Removes silent runtime drift while keeping one explicit narrow boundary.

**Addresses.** M1, M2, S002.

## D2 — `HarnessBundle` paired registry

**Decision.** Registry entries pair `adapter`, `connection_cls`, and `spec_cls` for each `HarnessId`.

**Why.** Keeps dispatch invariant explicit and auditable.

**Addresses.** M2, M8.

## D3 — Abstract factory enforcement is ABC + Protocol

**Decision.** `HarnessAdapter` remains Protocol for static structural checks, and `BaseSubprocessHarness(Generic[SpecT], ABC)` declares `@abstractmethod resolve_launch_spec(...)` for runtime instantiation rejection.

**Why.** Protocol conformance alone does not raise instantiation-time `TypeError`.

**Addresses.** E1, S001.

## D4 — Non-optional resolver contract

**Decision.** `PermissionResolver` is non-optional and requires `.config`.

**Why.** Deletes cast-to-None entry points and silent fallback chains.

**Addresses.** H3.

## D5 — Projection drift guard (both directions)

**Decision.** Use import-time helper `_check_projection_drift(...)` and compare expected vs accounted fields in both directions.

```python
expected = set(spec_cls.model_fields)
accounted = projected | delegated
if expected != accounted:
    missing = expected - accounted
    stale = accounted - expected
    raise ImportError(f"Projection drift: missing={sorted(missing)} stale={sorted(stale)}")
```

**Why.** Catches both newly added fields and stale removed names.

**Addresses.** H4, L1.

## D6 — SpawnParams accounting split

**Decision.** Keep `_SPEC_HANDLED_FIELDS` + `_SPEC_DELEGATED_FIELDS` accounting in `launch_spec.py`.

**Why.** Forces explicit ownership for every `SpawnParams` field.

**Addresses.** L2.

## D7 — Projection function set and naming

**Decision.** Standardize projection modules/functions:

- `project_claude.py`
- `project_codex_subprocess.py`
- `project_codex_streaming.py`
- `project_opencode_subprocess.py`
- `project_opencode_streaming.py`

Use `project_opencode_spec_to_session_payload` (not `...http_payload`).
Keep reserved-flag constants and stripping helper centralized in `src/meridian/lib/harness/projections/_reserved_flags.py`.

**Why.** Consistent axis and lower blast radius.

**Addresses.** M3, M4, F9, F28, F35.

## D8 — Claude permission-flag dedupe at projection site

**Decision.** Deduplicate/merge `--allowedTools` and `--disallowedTools` in Claude projection.

**Why.** One authoritative merge point across transports.

**Addresses.** H2.

## D9 — Canonical Claude ordering

**Decision.** One canonical projection order for subprocess and streaming Claude tails.

**Why.** Prevents transport ordering drift.

**Addresses.** M3.

## D10 — `agent_name` declaration scope

**Decision.** Inline `agent_name: str | None = None` directly on `ClaudeLaunchSpec` and `OpenCodeLaunchSpec`; do not keep a shared mixin at two call sites.

**Why.** Abstraction threshold not met (2 consumers). Re-extract only when a third semantically aligned consumer exists.

**Addresses.** L3 (not L5).

## D11 — `UnsafeNoOpPermissionResolver`

**Decision.** Rename `NoOpPermissionResolver` to `UnsafeNoOpPermissionResolver`; retain loud warning semantics.

**Note.** Unit tests may pass `_suppress_warning=True` to reduce fixture noise.

**Why.** Name must encode risk; unsafe behavior must be explicit.

**Addresses.** H3, F10, F36, F37.

## D12 — Shared `LaunchContext`

**Decision.** Both runners call `prepare_launch_context(...)` from `launch/context.py`.

**Why.** Centralizes launch-state assembly and removes runner duplication.

**Addresses.** M6.

## D13 — Constants/text util extraction

**Decision.** Shared constants live in `launch/constants.py`; shared text helpers (`dedupe_nonempty`, `split_csv_entries`) live in `launch/text_utils.py`.

**Why.** Closes per-harness utility duplication and addresses L5 smell.

**Addresses.** M6, L5.

## D14 — Confirm-mode event ordering semantics

**Decision.** Guarantee is: rejection event is enqueued before `send_error` is awaited.

**Why.** Deterministic call ordering without wall-clock assumptions.

**Addresses.** M9, S032.

## D15 — Codex spec shape

**Decision.** `CodexLaunchSpec` does not store `sandbox_mode` or `approval_mode`; projections read `spec.permission_resolver.config` directly.

**Why.** Removes duplicate state and H1-style stale field hazards.

**Addresses.** H1.

## D16 — `report_output_path` on Codex only

**Decision.** Keep `report_output_path` only on `CodexLaunchSpec`.

**Why.** Harness-specific feature.

**Addresses.** M5.

## D17 — OpenCode skills single-channel policy

**Decision.** Skills delivery channel is chosen at spec construction; projections do not choose channel dynamically.

**Why.** Avoid double-injection.

**Addresses.** M4.

## D18 — OpenCode connection inheritance

**Decision.** `OpenCodeConnection` inherits `HarnessConnection[OpenCodeLaunchSpec]`.

**Why.** Keep interface drift visible to type system.

**Addresses.** M8.

## D19 — Runner size budget + trigger

**Decision.** Full decomposition remains out of v2 scope, but post-v2 budget is mandatory:

- `runner.py <= 500` lines
- `streaming_runner.py <= 500` lines

If either exceeds budget after v2, raise L11 decomposition back into active scope immediately.

**Why.** Enforces structural health signal, avoids indefinite deferral.

**Addresses.** M6/L11 follow-through.

## D20 — Codex probe and fail-closed capability policy

**Decision.** Probe real `codex app-server --help` before finalizing mapping. If requested sandbox/approval semantics cannot be expressed, projection raises `HarnessCapabilityMismatch` and spawn fails before launch.

**Why.** No silent downgrade at integration boundary.

**Addresses.** H1, E38.

## D21 — Adapter-owned preflight contract

**Decision.** Add `preflight(...) -> PreflightResult` to `HarnessAdapter`; base returns empty result; Claude overrides for parent-permission forwarding and `--add-dir` injection.

**Why.** Removes harness-id branching from shared launch context and preserves Open/Closed boundaries.

**Addresses.** F5.

## D22 — Connection facet collapse

**Decision.** Remove `HarnessLifecycle` / `HarnessSender` / `HarnessReceiver` facet protocols in v2; keep single `HarnessConnection[SpecT]` ABC.

**Why.** Avoid duplicate interface declarations drifting out of sync.

**Audit.** `rg "HarnessLifecycle|HarnessSender|HarnessReceiver" src/` showed negligible consumer value for keeping facets.

**Addresses.** F20.

## D23 — Remove `mcp_tools` from `SpawnParams` in v2

**Decision.** Delete `mcp_tools` from launch-time spec/factory surface for v2.

**Why.** MCP wiring is explicitly out of scope and current adapters return no MCP config.

**Addresses.** F30.

## D24 — Shared missing-binary error class

**Decision.** Introduce `HarnessBinaryNotFound` in `src/meridian/lib/harness/errors.py` and use it across subprocess and streaming runners.

**Why.** Structured parity for PATH/binary failures.

**Addresses.** F33, S028.

## Revision Pass 1 (post p1422/p1423/p1425/p1426)

- F1: Unified `CodexLaunchSpec` shape; removed sandbox/approval fields from launch-spec examples and added D15 supersession note.
- F2: Updated Codex projection field sets to post-D15 shape and added resolver-config read example.
- F3: Clarified Protocol vs ABC roles; abstract-method instantiation enforcement now explicitly ABC-based.
- F4: Replaced `cast(Any, spec)` guidance with dispatch `isinstance` guard plus `cast(SpecT, spec)`.
- F5: Added adapter `preflight` contract and moved Claude preflight ownership behind adapter boundary.
- F6: Expanded completeness model to transport-wide accounted-field unions across all consumers.
- F7: Added reserved-flag policy and passthrough stripping/merge semantics with warning logs.
- F8: Added fail-closed Codex capability mismatch policy for unrepresentable sandbox/approval semantics.
- F9: Merged Codex streaming projections into `project_codex_streaming.py`.
- F10: Switched REST default to strict rejection; unsafe fallback gated by `--allow-unsafe-no-permissions`.
- F11: Corrected D5 sample to check both missing and stale drift directions.
- F12: Corrected D10 finding label to L3; documented L5 closure via text-utils extraction.
- F13: Reconciled S002 contract with dispatch-site runtime guard and no behavior-switching checks in connections.
- F14: Updated scenario module enumeration to full renamed projection module set and added `_PROJECTED_FIELDS` match-count meta assertion.
- F15: Corrected S033 OpenCode target function to `project_opencode_spec_to_serve_command`.
- F16: Added Codex streaming debug log for ignored `report_output_path` and delegated-field annotation.
- F17: Made continue-fork validator base-scoped so it applies to all harness specs.
- F18: Standardized guard testing on `_check_projection_drift` helper with synthetic spec classes.
- F19: Added `launch_types.py` DAG topology and moved shared leaf contracts there.
- F20: Chose facet collapse; connection surface is now single ABC contract.
- F21: Audited typed design guidance to remove `cast(Any, ...)` in favor of typed narrow casts.
- F22: Set authoritative cast location to `SpawnManager.start_spawn`; removed conflicting shared-core wording.
- F23: Reframed S016 requirement to semantic distinctness plus audit trail (not distinct wire strings per cell).
- F24: Declared `PermissionConfig.approval` as a `Literal` domain.
- F25: Tightened confirm-mode ordering guarantee to enqueue-before-await semantics.
- F26: Reconciled append-system-prompt policy to "both flags appear; user wins; warning emitted".
- F27: Added post-v2 runner line-budget target (500 each) with explicit L11 trigger.
- F28: Renamed projection modules to consistent `project_<harness>_<transport>.py` pattern.
- F29: Renamed shared launch module reference from `launch/core.py` to `launch/context.py`.
- F30: Removed `mcp_tools` from v2 launch spec/factory surface and documented decision.
- F31: Documented `_SPEC_HANDLED_FIELDS` limitation (global accounting, not per-adapter completeness).
- F32: Added explicit `BaseSubprocessHarness` default-method audit requirement in typed migration shape.
- F33: Added explicit `HarnessBinaryNotFound` structured error decision.
- F34: Tightened S015 verification to require explicit field-to-wire mapping table assertions.
- F35: Standardized OpenCode session payload function name to `project_opencode_spec_to_session_payload`.
- F36: Renamed all design/scenario references from `NoOpPermissionResolver` to `UnsafeNoOpPermissionResolver`.
- F37: Added `UnsafeNoOpPermissionResolver` warning-suppression note for unit-test fixtures.

## Revision Pass 2 (post p1429/p1430)

- G1: Completed `typed-harness.md` import topology DAG with all v2 modules (`harness/errors.py`, `harness/claude_preflight.py`, `harness/bundle.py`, `launch/constants.py`, `launch/context.py`, `launch/text_utils.py`, `projections/_guards.py`, `projections/_reserved_flags.py`) and explicit upward edges; linked from overview §5.
- G2: Added `typed-harness.md` §Bundle Registry with canonical `HarnessBundle[SpecT]`, `_REGISTRY`, and `get_harness_bundle(harness_id)` contract; referenced registry consumption from shared-core context assembly.
- G3: Pinned reserved-flag constants/strip helper to `projections/_reserved_flags.py`; updated `permission-pipeline.md` and `transport-projections.md` imports/policy examples to use the canonical path.
- G4: Set `launch/launch_types.py` as single home for `ResolvedLaunchSpec` base body and `continue_fork` validator; replaced duplicated base block in `launch-spec.md` with a direct reference.
- G5: Added `launch/text_utils.py` to module-layout sections and documented its shared responsibilities in `runner-shared-core.md` and `overview.md`.
- G6: Removed `PreflightResult.extra_cwd_overrides`; shared-core env merge now uses `plan.env_overrides`, runtime overrides, and `preflight.extra_env` only.
- G7: Removed `LaunchContext.permission_config` duplicate state; context consumers now read `ctx.perms.config`.
- G8: Reworked Codex streaming accounting to per-consumer accounted sets tied to concrete consumer functions/modules, with explicit aggregation and clarified `interactive` ownership in env-building consumer.
- G9: Inlined `agent_name` on `ClaudeLaunchSpec` and `OpenCodeLaunchSpec`; deleted `_AgentNameMixin` in design samples and updated D10 accordingly.
- G10: Simplified Codex streaming drift check by removing one-off `_SPEC_DELEGATED_FIELDS` indirection and validating with `delegated=frozenset()`.

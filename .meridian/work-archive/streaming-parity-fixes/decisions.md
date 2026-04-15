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

> **Superseded by K9 (Revision Pass 3):** the per-adapter `handled_fields` union is now authoritative. `_SPEC_HANDLED_FIELDS` is retained only as a derived alias `frozenset(SpawnParams.model_fields)` — no manual enumeration. `_SPEC_DELEGATED_FIELDS` is deleted (G10 already removed it for the Codex streaming case).

**Decision.** Keep `_SPEC_HANDLED_FIELDS` + `_SPEC_DELEGATED_FIELDS` accounting in `launch_spec.py`.

**Why.** Forces explicit ownership for every `SpawnParams` field.

**Addresses.** L2.

## D7 — Projection function set and naming

> **Superseded in part by H1 (Revision Pass 3):** the reserved-flag constants / stripping helper / `projections/_reserved_flags.py` module are **deleted**. The projection module naming convention (`project_<harness>_<transport>.py`) remains current.

**Decision.** Standardize projection modules/functions:

- `project_claude.py`
- `project_codex_subprocess.py`
- `project_codex_streaming.py`
- `project_opencode_subprocess.py`
- `project_opencode_streaming.py`

Use `project_opencode_spec_to_session_payload` (not `...http_payload`).
~~Keep reserved-flag constants and stripping helper centralized in `src/meridian/lib/harness/projections/_reserved_flags.py`.~~ *(deleted by H1)*

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

> **Superseded by H4 (Revision Pass 3):** `mcp_tools: tuple[str, ...] = ()` is restored as a first-class field on `ResolvedLaunchSpec` with per-harness projection mappings. Manual `mcp_tools` configuration works today even though auto-packaging through mars is still out of scope for v2.

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

## Revision Pass 3 (post p1433/p1434/p1435) — Reframe as Coordinator

Three independent audits converged on the same picture: rounds 1–2 combined genuine internal-consistency gaps with overreach into user and harness behavior. Round 3 separates the two. Meridian is a coordinator, not a policy engine. Every strict check answers "does this protect against meridian's own internal drift?" If not, it's deleted.

> **Labeling note.** Round 3 entries use the `H#` (historical / round 3) and `K#` (keeper invariant) namespaces. These are distinct from the legacy `D#` decisions at the top of this file. Legacy `D#` IDs that Round 3 supersedes are marked **Superseded by H#** in place — do not confuse round 3 `H#` entries with legacy `D#` entries.

### Dropped — Overreach

- **H1:** **Deleted** all reserved-flag machinery. `_RESERVED_CODEX_ARGS`, `_RESERVED_CLAUDE_ARGS`, `strip_reserved_passthrough`, the `projections/_reserved_flags.py` module, any `strip` / heuristic / probe-derived inventories. `extra_args` is forwarded verbatim to every transport. Meridian is not the security gate for passthrough flags; the harness is. Users can invoke the harness directly with the same flags — meridian silently stripping them is worse than forwarding them. **Supersedes: D7 (reserved-flag module pin), F7 (reserved-flag policy), F28 (reserved-flag renames).**
- **H2:** **Rejected** adding a `@model_validator` that validates `PermissionConfig` combinations like `approval=confirm + sandbox=yolo`. If the harness accepts the combo, meridian accepts it. Meridian is not the authority on which combinations make semantic sense.
- **H3:** **Rejected** any `_FORBIDDEN_FIELD_PREFIXES = frozenset({"mcp_"})`-style import-time check on `SpawnParams` field names. Special-casing against a specific string prefix is hacky; the existing projection drift guard already catches "field with no consumer".

### Restored — Reversing round 2 overreach

- **H4:** **Restored** `mcp_tools: tuple[str, ...] = ()` as a first-class field on `ResolvedLaunchSpec` (reversing round 2 D23, which removed `mcp_tools` in F30). Projections map it to Claude `--mcp-config`, Codex `-c mcp.servers.X.command=...`, and OpenCode HTTP session payload `mcp` field. Auto-packaging through mars is still out of scope for v2; manual `mcp_tools` configuration works today. The projection drift guards count it as a normal field with no special handling. **Supersedes: D23, F30.**
- **H5:** **Retained** `PermissionConfig` Literals for now, with a documented friction-free extension path: adding a new sandbox tier or approval mode is a one-line edit to the tuple plus per-harness projection mapping updates. No runtime probing, no `--help` parsing, no auto-detection. Literals are developer-facing documentation and type-checker support, not a runtime gate.

### Kept — Real internal-consistency invariants

- **K1:** Bundle dispatch is keyed on `(harness_id, transport_id)`. `HarnessBundle[SpecT]` carries a `connections: Mapping[TransportId, type[HarnessConnection[SpecT]]]` mapping. Adding Claude-over-HTTP in the future is a one-line bundle addition, not a rewiring of dispatch. `typed-harness.md §Dispatch Boundary` is updated; `HarnessId` and `TransportId` live in a single home at `meridian.lib.harness.ids` (see F13 / ID location pin). **Extends D2 (paired registry); the new structure is the `HarnessBundle[SpecT]` with a transport mapping.**
- **K2:** Bundle registration goes through a single `register_harness_bundle(bundle)` helper that validates duplicate `harness_id`, non-None `extractor`, and non-empty `connections` mapping, raising `ValueError` / `TypeError` as appropriate. `harness/__init__.py` imports every concrete adapter module eagerly so registration happens before the first dispatch. Unit test S039 asserts duplicate registration fails; S043 asserts missing-extractor registration fails.
- **K3:** `BaseHarnessAdapter.id` and `BaseHarnessAdapter.handled_fields` are `@abstractmethod`, reconciling the `HarnessAdapter` Protocol method set against the ABC abstract-method set. A subclass that forgets `id` or `handled_fields` now fails at instantiation with `TypeError` instead of crashing deep in dispatch with `AttributeError`. Unit test S040 cross-checks Protocol attributes vs ABC abstractmethods. **Note:** `BaseHarnessAdapter` is the round-3 rename of `BaseSubprocessHarness` (all adapters inherit it regardless of transport — the old name was misleading).
- **K4:** `PermissionResolver.resolve_flags()` no longer takes a `harness` parameter. The old signature `resolve_flags(self, harness: HarnessId)` invited `if harness == CLAUDE` branching inside the resolver, re-introducing the harness-id dispatch `adapter.preflight()` was meant to eliminate. New shape: resolvers expose intent via `config`; projections translate per harness. Chose option (a) from the brief (drop the parameter entirely) because it cleanly forbids harness branching rather than relying on documented restraint. **Mechanical enforcement:** scenario S052 uses `inspect.signature` + an AST scan (`rg "HarnessId" src/meridian/lib/permission*`) to block re-introduction of harness branching in any resolver implementation. The old "enforced by convention" wording in `permission-pipeline.md` is replaced by this mechanical guard.
- **K5:** `RuntimeContext.child_context()` is the sole producer of `MERIDIAN_*` runtime overrides. `RuntimeContext` produces the full canonical key set `_ALLOWED_MERIDIAN_KEYS = frozenset({"MERIDIAN_REPO_ROOT", "MERIDIAN_STATE_ROOT", "MERIDIAN_DEPTH", "MERIDIAN_CHAT_ID", "MERIDIAN_FS_DIR", "MERIDIAN_WORK_DIR"})`. `merge_env_overrides(...)` enforces the invariant: if **either** `plan_overrides` or `preflight.extra_env` contains any `MERIDIAN_*` key, it raises `RuntimeError`. Scenarios S046 (preflight) and S046b (plan) exercise this. **Rationale for widening:** the original spec blocked only `preflight.extra_env`, leaving `plan_overrides` as an ambient back-door for `MERIDIAN_FS_DIR` / `MERIDIAN_WORK_DIR`. Opus review p1439 flagged this; widening restores the "sole producer" claim.
- **K6:** Pulled session-id extraction parity into v2 scope. Added `HarnessExtractor[SpecT]` to `HarnessBundle`. Subprocess and streaming both call `bundle.extractor.detect_session_id_from_artifacts(spec, launch_env, child_cwd, state_root)` for fallback detection from harness-specific artifacts (Claude project files, Codex rollout files, OpenCode logs). The signature threads `launch_env` so extractors respect non-default `CODEX_HOME`/`OPENCODE_*` paths set via `preflight.extra_env`. Closes the p1385 gap that streaming had no fallback session detection. Chose pull-in over explicit deferral because the design absorbed it without blowing scope. **Enforcement point:** `register_harness_bundle(...)` validates `bundle.extractor is not None` at registration time (S043 targets this), and the `HarnessExtractor` Protocol is `runtime_checkable` so `isinstance` checks catch stub mismatches.
- **K7:** `PermissionConfig` is now `model_config = ConfigDict(frozen=True)`. `PreflightResult.extra_env` is wrapped in `MappingProxyType` at construction. `LaunchContext.env` / `env_overrides` are wrapped in `MappingProxyType`. This is about internal-state integrity (meridian's own coordination depends on stable values during merge + projection), not about validating values.
- **K8:** Added explicit cancel/interrupt/SIGTERM semantics table to `typed-harness.md §Connection Contract`. `send_cancel` and `send_interrupt` are idempotent and converge to a single terminal spawn status. Runner signal handling is transport-neutral — SIGTERM/SIGINT translate into exactly one `send_cancel()` per active connection. Cancellation event emission is exactly-once per spawn, ordered before any subsequent error emission. Scenarios S041 (cancel idempotency), S042 (SIGTERM subprocess/streaming parity), S048 (race: cancel vs completion terminal status).
- **K9:** Added per-adapter `handled_fields: frozenset[str]` declaration, split into `consumed_fields | explicitly_ignored_fields` per Opus finding #8 — "listed but not wired" is a conscious opt-out. `harness/launch_spec.py` aggregates the union across registered bundles and asserts it equals `SpawnParams.model_fields` via `_enforce_spawn_params_accounting(registry=_REGISTRY)`. The function takes an injectable `registry` parameter so S044 can drive it with a fixture registry without mutating global state. Legacy `_SPEC_HANDLED_FIELDS` is now `frozenset(SpawnParams.model_fields)` — a derived alias kept only for test-fixture ergonomics, with no manual enumeration. **Supersedes: D6 (`_SPEC_HANDLED_FIELDS` as manually maintained), F31 (authoritative-global framing).**

### Clarifications

- **C1:** `LaunchContext` parity claim narrowed to the deterministic subset — `run_params`, `spec`, `child_cwd`, `env_overrides`. The `env` field as a whole depends on ambient `os.environ` and is explicitly NOT in the parity contract. S024 updated to assert parity on the deterministic subset only.
- **C2:** Added eager-import note to `transport-projections.md §Eager Import Bootstrapping`. `harness/__init__.py` imports every projection module so drift guards always execute at package load, not after the first dispatch. A canonical `harness/__init__.py` bootstrap block lives in `typed-harness.md §Bootstrap Sequence` — it names the exact import order and pins `_enforce_spawn_params_accounting()` as the final explicit call (not a module-load side effect).
- **C3:** Added soft line-budget marker to `transport-projections.md §Codex Streaming Projection`. If `project_codex_streaming.py` exceeds 400 lines, split into `project_codex_streaming_appserver.py` + `project_codex_streaming_rpc.py`, with `_ACCOUNTED_FIELDS` aggregated in `project_codex_streaming_fields.py` (both splits import from it). The single `_check_projection_drift(...)` call lives in `project_codex_streaming.py` which re-exports the split functions. Follow D19 precedent.

### Retired scenarios

- S037 (reserved-flag stripping) is **retired** and replaced by S045 ("extra_args forwarded verbatim"). E37 is removed from `edge-cases.md`. E48 is the new verbatim-passthrough edge case.
- S023 (allowed-tools merged from resolver + extra_args) is **updated** to reflect verbatim forwarding: both flags appear, no merge, no strip.
- S011 / S012 are **retained but scoped** to resolver-internal dedupe only (multi-source merge inside the resolver), not dedupe against user `extra_args`.

### New scenarios

- S039 — Duplicate bundle registration raises `ValueError`.
- S040 — Protocol/ABC method-set reconciliation test.
- S041 — `send_cancel` idempotency.
- S042 — SIGTERM parity across subprocess and streaming.
- S043 — Missing extractor in bundle fails at registration.
- S044 — New `SpawnParams` field without an adapter owner fails at import time.
- S045 — `extra_args` forwarded verbatim to every transport (replaces S037).
- S046 — `preflight.extra_env` containing `MERIDIAN_*` raises in `merge_env_overrides`.
- S047 — `mcp_tools` projects to every harness's wire format.
- S048 — Cancel vs completion race: exactly-one terminal status persisted.
- S049 — Streaming session-id fallback via `HarnessExtractor`.
- S050 — `(harness, transport)` dispatch for unsupported transport raises `KeyError`.
- S051 — `PermissionConfig` frozen: mutation raises.

## Revision Pass 3 — Convergence Fixes (post p1437/p1438/p1439/p1440)

Four independent reviewers (gpt-5.4, gpt-5.2, claude-opus-4-6, refactor-reviewer) returned `changes-required` on the round-3 reframe. Convergent findings and opus-specific critical findings applied here, tagged `F#` (round-3 convergence fixes). These do not reverse any H/K entry — they harden enforcement, fix traceability, and close gaps reviewers surfaced.

- **F1 (decision-ID collision):** Dropped all `H# (D#)` parenthetical aliases in Revision Pass 3; the `D#` slots collided with legacy decisions D1-D24. Round 3 entries are now `H#` / `K#` only. Added a labeling note at the top of the Revision Pass 3 section.
- **F2 (superseded markers):** Added explicit "Superseded by H#" markers to legacy D6, D7, and D23 where round 3 reverses or replaces them. F7/F28 are flat revision-1 ledger entries and are referenced by H1's `Supersedes:` list rather than marked inline.
- **F3 (bundle registration validation):** `register_harness_bundle(bundle)` now validates `extractor is not None` and non-empty `connections` at registration time, raising `TypeError`/`ValueError`. Previously the design claimed this invariant but placed enforcement ambiguously between eager-import bootstrap and dataclass construction — neither of which actually fires at registration. S043 targets the registration-time check.
- **F4 (accounting registry parameter):** `_enforce_spawn_params_accounting(registry=None)` now accepts an injectable registry with `_REGISTRY` as the default, so S044 can exercise the check with a fixture registry without polluting module-global state.
- **F5 (S047 anchor fix):** S047 Source line updated from `decisions.md D4` to `decisions.md H4` — the old anchor pointed at the legacy D4 (non-optional resolver contract), not at the restored `mcp_tools` entry.
- **F6 (canonical `harness/__init__.py` bootstrap):** Added a §Bootstrap Sequence section to `typed-harness.md` that spells out the full load-bearing import sequence in one block: concrete adapters → projection modules → extractors → explicit `_enforce_spawn_params_accounting()` call. Moved the accounting call out of module-load side effects in `launch_spec.py` so import order is deterministic and S044 is not flaky.
- **F7 (K4 mechanical guard):** Replaced the "enforced by convention" wording in `permission-pipeline.md` with a mechanical guard: scenario S052 asserts `inspect.signature(PermissionResolver.resolve_flags)` has no `harness` parameter and runs `rg HarnessId src/meridian/lib/permission*` as a CI regression check.
- **F8 (S024 narrowing):** S024 Verification updated to assert parity only on `run_params`, `spec`, `child_cwd`, `env_overrides` — dropping the broad `.env == .env` assertion that contradicted C1.
- **F9 (K5 plan_overrides widening):** `merge_env_overrides` now rejects `MERIDIAN_*` keys in **both** `preflight_overrides` and `plan_overrides`. `RuntimeContext` produces the full `_ALLOWED_MERIDIAN_KEYS` set including `MERIDIAN_FS_DIR` and `MERIDIAN_WORK_DIR`. Scenario S046b added for the plan_overrides side.
- **F10 (`_SPEC_HANDLED_FIELDS` derivation):** `_SPEC_HANDLED_FIELDS = frozenset(SpawnParams.model_fields)` — derived, not manually enumerated. Eliminates the dual-authority drift risk the refactor-reviewer flagged.
- **F11 (S047 OpenCode subprocess pin):** S047 now pins one concrete OpenCode-subprocess behavior: `mcp_tools` is rejected with a clear error from `project_opencode_subprocess` because OpenCode subprocess has no wire format for MCP config. The HTTP streaming path carries the full `mcp` session-payload field. No "env-only fallback" vagueness.
- **F12 (`HarnessExtractor` signature widening):** `detect_session_id_from_artifacts(spec, launch_env, child_cwd, state_root)` now takes `launch_env: Mapping[str, str]` so extractors honor non-default `CODEX_HOME` / `OPENCODE_*` paths set via `preflight.extra_env`.
- **F13 (`HarnessId` / `TransportId` single home):** Both enums live in `meridian.lib.harness.ids`. Previous drafts implied three locations (`ids`, `core.types`, "next to `HarnessId`"); this fix pins one module.
- **F14 (E36/E38 scenario anchors):** S036 and S038 Source lines updated to cite `design/edge-cases.md E36` / `E38` explicitly.
- **F15 (delete free-TypeVar cast):** `cast(SpecT, spec)` removed from `dispatch_start` — `SpecT` is not bound in that scope and the `isinstance(spec, bundle.spec_cls)` guard is the actual safety narrow.
- **F16 (`BaseSubprocessHarness` rename):** Renamed to `BaseHarnessAdapter` across all docs and scenarios. The old name misled readers into expecting a `BaseStreamingHarness` that does not exist.
- **F17 (import topology arrows):** Committed to one arrow convention in `typed-harness.md §Import Topology` — "A → B means A imports B". Added missing edges from `bundle.py` to `adapter.py`, `connections/base.py`, `extractors/base.py`.
- **F18 (S031 stale path):** S031 updated to reference `launch/launch_types.py` (the current layout) instead of the stale `harness/launch_types.py` path.
- **F19 (line-budget split rule pin):** §Line Budget in `transport-projections.md` now names `project_codex_streaming_fields.py` as the shared module that holds `_ACCOUNTED_FIELDS` after a split, and specifies that the single `_check_projection_drift(...)` call stays in `project_codex_streaming.py`.
- **F20 (`handled_fields` split):** Per Opus finding #8, `BaseHarnessAdapter` now exposes `consumed_fields` and `explicitly_ignored_fields` as separate `@property` sets, with `handled_fields = consumed_fields | explicitly_ignored_fields`. The projection-side `_PROJECTED_FIELDS` drift guard cross-references against `consumed_fields` so "listed but not wired" is caught.
- **F21 (S046b):** New scenario `plan_overrides` containing `MERIDIAN_*` raises in `merge_env_overrides`. Paired with widened K5 guarantee (F9).

### New scenarios (Convergence Pass)

- **S052** — `PermissionResolver.resolve_flags()` has no `harness` parameter; resolvers do not import `HarnessId` (K4 mechanical guard).
- **S046b** — `plan_overrides` containing `MERIDIAN_*` raises in `merge_env_overrides` (K5 widening).

## E1 — Phase 1 execution decisions

- **E1.1 — Temporary `_NoOpPermissionResolver` default on `ResolvedLaunchSpec.permission_resolver`.** Phase 1 kept a pydantic `default_factory=_NoOpPermissionResolver` on the base spec field so existing call sites (harness tests, REST spawn helpers, streaming runner) still construct specs without an explicit resolver. This is an intentional temporary bridge between the v1 shape, where resolver was implicitly `None`, and the v3 target, where resolver is non-optional. Phase 2 deletes the default and replaces bare call sites with explicit `UnsafeNoOpPermissionResolver()` or a real resolver. Ref: `design/permission-pipeline.md`, D4, H3.
- **E1.2 — Temporary `ResolvedLaunchSpec.permission_config` compat property.** The p1444 verifier added a read-only `permission_config` passthrough over `self.permission_resolver.config` so older call sites reading `spec.permission_config` still work. This is compat carrying. Phase 2/3 updates every consumer to read from `spec.permission_resolver.config` and deletes the property.
- **E1.3 — Adapter-level `continue_fork` normalization.** During S020 verification it surfaced that the legacy adapters (Claude, Codex, OpenCode) passed `continue_fork=run.continue_fork` while `run.continue_harness_session_id` could be `None`, so the restored base-spec validator raised `ValueError` for previously-working call sites. Adapters now normalize `continue_fork=False` when there is no session id. Recorded as scenario S053. This keeps S020's validator invariant intact while preserving the existing silent no-op runtime behavior that call sites depend on.
- **E1.4 — Phase 1 verifier overreach.** The p1444 verifier initially removed `_validate_continue_fork_requires_session` from `ResolvedLaunchSpec` citing "existing harness behavior already treats fork-without-session as a no-op". That was out of scope for the verifier role and regressed S020 directly. The p1445 unit-tester restored the validator and fixed the three adapters that exposed the actual drift (E1.3). Recorded so future phases know the validator stays in place.

## E2 — Phase 2 execution decisions

### E2.1 — S051 scope narrowing, LaunchContext clause split to S054

**What:** Narrowed S051 to cover only `PermissionConfig` + `PreflightResult.extra_env` immutability during Phase 2. Split the `LaunchContext.env / env_overrides` clause into a new scenario **S054** assigned to Phase 6, where `LaunchContext` is actually defined.

**Why:** The @unit-tester (p1449) found that S051's third clause referenced `LaunchContext.env`, but `LaunchContext` does not yet exist in the tree — it is a Phase 6 artifact per plan/phase-6 and scenario S024. Phase 2 cannot verify immutability of a type that hasn't been implemented. Phase 2 owns the contract leaves; Phase 6 owns the runner-side launch context. The correct fix is to align the scenario with the phase that owns the implementation, not to pull `LaunchContext` forward into Phase 2.

**Alternatives rejected:**
- Creating a stub `LaunchContext` in Phase 2: would bleed Phase 6 concerns into Phase 2 and duplicate work when Phase 6 designs the real contract.
- Deferring all of S051 to Phase 6: would leave `PermissionConfig` immutability unverified during Phase 2 even though it was already implemented and passing tests.

**Impact:** S051 flips to verified in Phase 2 for clauses (a) and (b). S054 is a new Phase 6 scenario covering clause (c). scenario-ownership.md updated accordingly. Phase 2 can close; Phase 6 picks up S054 alongside S024.

## E3 — Phase 3 execution decisions

### E3.1 — Claude flag-collision semantics are explicit, not rewritten

**What:** Phase 3 keeps Meridian-managed Claude flags in canonical order, then appends user `extra_args` verbatim in the tail. If the same flag appears in both places (`--append-system-prompt`, `--allowedTools`, `--disallowedTools`), both are forwarded and the later user tail copy wins by Claude last-wins behavior.

**Why:** This matches the round-3 coordinator boundary: Meridian does not strip or rewrite user passthrough.

**Wire quirk rediscovered:** Claude accepts repeated instances of these flags, and effective behavior follows argument order (later flag value wins).

### E3.2 — Parent Claude allowlist forwarding stays resolver-internal via adapter preflight

**What:** Claude adapter preflight now forwards parent allowlist values via an internal sentinel passthrough token (`--meridian-parent-allowed-tools`) that is consumed by `project_claude_spec_to_cli_args` before launch. Projection merges those values with resolver-emitted `--allowedTools` into one deduped managed flag.

**Why:** Preserves S011/S012 resolver-internal dedupe while keeping S023's user passthrough boundary intact.

**Wire quirk rediscovered:** Parent-forwarded allowlist values and resolver values can overlap; dedupe must preserve first-seen order (`Read,Edit,Bash` style unions) to keep deterministic CLI tails across subprocess and streaming.

### E3.3 — Env var block asymmetry stays deferred to Phase 6/7

**What:** `ClaudeAdapter.blocked_child_env_vars()` returns `{"CLAUDECODE"}` while the streaming `claude_ws._BLOCKED_CHILD_ENV_VARS` set also includes `{"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"}`. The extra streaming-only entry is intentional: streaming sessions should not inherit the parent autocompact override.

**Why:** The split currently lives in two unrelated places, but that is still consistent with the subprocess/streaming parity thesis. Consolidate when Phase 6 introduces shared launch-context env helpers or Phase 7 handles projection convergence.

**Impact:** No Phase 3 action. Tracked as handoff to Phase 6/7.

## E4 — Phase 4 execution decisions

### E4.1 — `codex exec` approval flag surface changed; config override is canonical

**What:** Re-probed `codex-cli 0.118.0` and confirmed `codex exec` rejects both `--ask-for-approval` and `-a` as unknown arguments. `-c approval_policy=...` is accepted and is the only stable approval-policy control on this binary surface.

**Why:** D16/D20/G8 require fail-closed projection instead of silent downgrade when requested permission semantics cannot be represented. With no top-level approval flag, Meridian must project approval intent via `-c approval_policy=...`.

**Wire quirk rediscovered:** `--full-auto` help text still references `-a on-request` even though `-a` is no longer accepted on this CLI build.

### E4.2 — Codex approval/sandbox mapping pinned to app-server/thread schema enums

**What:** Generated app-server JSON schema (`codex app-server generate-json-schema --out <dir>`) and pinned streaming request mappings to v2 thread params:
- `approvalPolicy`: `untrusted | on-failure | on-request | never`
- `sandbox`: `read-only | workspace-write | danger-full-access`

Meridian mapping now uses:
- `approval=auto -> on-request`
- `approval=confirm -> untrusted`
- `approval=yolo -> never`
- `approval=default -> no override`

- `sandbox=default -> no override`
- non-default sandbox modes pass through as-is.

**Why:** Keeps subprocess (`codex exec`) and streaming (`thread/*`) on one canonical semantic mapping.

### E4.3 — Fail-closed boundary implemented in both Codex projection paths

**What:** Added `HarnessCapabilityMismatch` and wired it into both:
- `project_codex_spec_to_cli_args(...)` (subprocess)
- `project_codex_spec_to_thread_request(...)` (streaming bootstrap)

If a requested approval/sandbox mode cannot be mapped on this Codex surface, projection raises before launch.

**Why:** This is D20/E38’s load-bearing boundary: no silent downgrade from requested permission semantics.

### E4.4 — Streaming app-server command now projects permission config directly

**What:** Streaming now builds `codex app-server` command via shared projection and includes:
- `-c sandbox_mode=...` when non-default
- `-c approval_policy=...` when non-default
- projected Codex MCP `-c mcp.servers.<name>.command=...` entries
- passthrough `extra_args` verbatim at the tail

**Why:** Removes hand-built command drift between connection and adapter paths.

### E4.5 — Confirm-mode approval rejection emits queue event before JSON-RPC error

**What:** In `codex_ws` request-approval handling, Meridian now enqueues
`warning/approvalRejected` before awaiting `_send_jsonrpc_error(...)`.

**Why:** Implements D14/D20/S032 ordering semantics using call sequence (enqueue-before-await), not timing.

### E4.6 — `report_output_path` split pinned: subprocess-only wire, streaming debug-ignore

**What:**
- Subprocess Codex projection keeps `-o <path>` when non-interactive.
- Streaming Codex projection does not emit a wire field for `report_output_path` and logs:
  `Codex streaming ignores report_output_path; reports extracted from artifacts`

**Why:** Implements D16/S019 exactly without leaking Codex subprocess-only behavior into streaming wire protocol.

### E4.7 — Phase 4 closure note — unit tester blocker superseded by smoke tester

**Phase 4 closure note — unit tester blocker superseded by smoke tester.** Unit tester p1462 observed `Operation not permitted (os error 1)` when trying to launch `codex app-server` from within its sandbox, and honestly flipped S007/S009 to `blocked` since it could not run a live round trip. Smoke tester p1463, running with full capability, booted `codex app-server` in three parametrized configs (`sandbox=read-only`, `sandbox=workspace-write`, `default/default`), completed JSON-RPC `initialize` + `thread/start` sessions, and obtained real `threadId`s for each. The projection is correct on both layers (command line + bootstrap payload); the unit tester's blocker was environmental, not a defect. Scenarios S007 and S009 are closed as `verified` on the strength of the smoke tester's real-binary evidence.

Recorded non-blocking observations from the smoke tester worth tracking:
- `PermissionConfig` has two layers of fail-closed: Pydantic Literal rejects invalid modes at construction time, and the projection mapper raises `HarnessCapabilityMismatch` against future drift. Tests monkeypatch the mapper to exercise the lower layer.
- `logger.debug(...)` is used for the `report_output_path` streaming-ignore note; users at INFO level will not see it. Consistent with the scenario contract, but flag if a future review wants more visible telemetry.
- `--full-auto` help text still references the stale `-a on-request` wording even though `-a` is no longer a real top-level flag. Cosmetic only.

## E5 — Phase 5 execution decisions

### E5.1 — `opencode serve` HTTP contract re-probed and pinned (2026-04-10)

**What:** Re-probed `opencode run --help`, `opencode serve --help`, and a live `opencode serve --pure` instance (`version: 1.4.3`) before finalizing OpenCode projection wiring.

**Observed contract:**
- Health: `GET /global/health` returns JSON (`{"healthy":true,...}`); `GET /health` returns the web UI HTML shell.
- Session creation: `POST /session` with JSON body returns JSON object containing `id` (session id).
- Message posting: `POST /session/{id}/message` requires `parts: [...]`; `{text: ...}` / `{message: ...}` return `400 invalid_type` for missing `parts`.
- Event stream: `GET /global/event` (and `/event`) returns `text/event-stream`; `/session/{id}/events` returns HTML shell.
- Alternate plural paths (`/sessions`, `/sessions/{id}/...`) return HTML shell rather than API JSON.
- Session action: `POST /session/{id}/abort` returns JSON `true`; `cancel`/`interrupt` path variants return HTML shell.

**Impact:** Streaming connection keeps path probing fallback logic, but projection now treats `/session`, `/session/{id}/message`, and `/global/event` as canonical OpenCode HTTP surfaces.

### E5.2 — Skills single-channel policy pinned at spec construction

**What:** OpenCode `resolve_launch_spec(...)` now chooses one authoritative skills channel per launch:
- default (`run_prompt_policy().include_skills=True`): skills are prompt-inlined by shared prompt composition, and `OpenCodeLaunchSpec.skills=()`.
- optional non-inline mode (`include_skills=False`): `OpenCodeLaunchSpec.skills` is populated and only the streaming session payload carries `skills`.

**Why:** Fixes double-send drift where skills were both inline in prompt and duplicated in HTTP payload.

### E5.3 — OpenCode subprocess/streaming MCP split is fail-closed

**What:**
- Subprocess projection (`opencode run`) now raises `HarnessCapabilityMismatch` when `mcp_tools` is non-empty.
- Streaming session payload projects `mcp_tools` into `mcp: [...]` on `POST /session`.

**Why:** `opencode run` has no per-spawn MCP wire format; silently dropping requested MCP tools is incorrect.

### E5.4 — Continue/fork transport semantics are explicit

**What:**
- Subprocess keeps explicit `--session ... --fork` behavior.
- Streaming session payload builder raises `HarnessCapabilityMismatch` when `continue_fork=True`.

**Why:** The current `opencode serve` `/session` API does not expose fork-on-continue semantics. Phase 5 requires fail-closed behavior rather than silent resume/new-session fallback.

### E5.5 — OpenCode model normalization occurs exactly once

**What:** OpenCode adapter normalizes model identifiers in `resolve_launch_spec(...)` only:
- strip one leading `opencode-` prefix when present
- normalize `provider/model` shape by splitting once on `/` and trimming

Both subprocess and streaming projections consume the resolved `spec.model` verbatim.

### E5.6 — Smoke tester real-binary observations (2026-04-11)

**Binary version:** `opencode 1.4.3` (confirmed by `opencode --version`).

**`POST /session` response shape:** `{"id": "ses_...", "slug": "...", "version": "1.4.3", "projectID": "global", "directory": "...", ...}`. Session ID key is `"id"`, not `"sessionId"` or `"sessionID"`. The `_extract_session_id_from_mapping` helper covers this correctly via its `("session_id", "sessionId", "sessionID", "id")` lookup chain.

**Unknown payload keys accepted silently:** `skills`, `mcp`, and invalid `sessionID` references all return HTTP 200 with a newly created session — server does not reject unknown fields. Invalid `sessionID` causes a fresh session rather than an error; callers should not rely on server-side rejection for invalid resumes.

**Health is `/global/health`:** Returns `{"healthy": true, ...}` (JSON). `/health` returns the web UI HTML shell — the server's path probing fallback order is critical.

**Server logs to stderr:** Confirms `stdout=DEVNULL, stderr=<file>` wiring in `_launch_process` is correct. Log format: `INFO  <ISO-TS> +<ms>ms service=<name> ...`.

**Failing test identified:** `tests/harness/test_launch_spec.py::test_opencode_subprocess_projection_logs_model_flag_collision_and_keeps_tail` FAILS. The test expects a DEBUG log when `extra_args` contains a `-m`/`--model` collision with the already-projected `--model` flag. The projection does append `extra_args` verbatim (assertion on `command[-3:]` passes), but `project_opencode_spec_to_cli_args` never emits the expected collision log. Fix needed in `project_opencode_subprocess.py`.

### E5.7 — Phase 5 fix loop closed the collision-log gap

**What:** Phase 5 initial implementation (p1465) wired subprocess projection, streaming projection, single-skills channel, model normalization, and `HarnessConnection[OpenCodeLaunchSpec]` inheritance. Parallel testers (unit p1466, smoke p1467) converged on one real gap: `project_opencode_spec_to_cli_args` appended colliding `extra_args` verbatim at the tail (correct) but emitted no DEBUG collision log (incorrect per Claude/Codex pattern). Fix coder p1468 added `_has_flag` / `_log_collision_if_needed` helpers covering `--model`/`-m`, `--variant`, `--agent`, `--session`/`-s`, `--continue`/`-c`, and `--fork`, mirroring the Claude projection's collision detection shape.

**Why:** The "resolver-internal dedupe allowed; cross-dedupe with user extra_args forbidden (last-wins)" contract requires visibility into the collision. Log at DEBUG (not WARNING) because the user tail-wins behavior is intentional, not a fault. The logging is telemetry for troubleshooting double-flag situations, not an error signal.

**Gates at closure:** all seven gates green (ruff, pyright, `test_opencode_http.py`, `test_launch_spec.py -k opencode`, `test_launch_spec_parity.py`, `test_streaming_runner.py`, full pytest excluding smoke). Scenarios S017, S018, S034 all marked `verified` with extra coverage in `test_launch_spec.py`, `test_opencode_http.py`, and `test_launch_spec_parity.py`.

## E6 — Phase 6 execution decisions

### E6.1 — `prepare_launch_context(...)` is the single shared prep path

**What:** Both `src/meridian/lib/launch/runner.py` and `src/meridian/lib/launch/streaming_runner.py` now go through `prepare_launch_context(...)` to produce the deterministic `(run_params, spec, child_cwd, env_overrides)` tuple. `LaunchContext` holds the resolved state with `env` and `env_overrides` as `MappingProxyType` views.

**Why:** Phase 6 parity contract (S024) plus K5 fail-closed merge behavior required a single authoritative prep path. Shared constants now live in `src/meridian/lib/launch/constants.py`; no private duplicates remain in either runner (S026 verified by @verifier p1473).

### E6.2 — `MERIDIAN_*` child overrides are produced only by `RuntimeContext.child_context()`

**What:** `merge_env_overrides(...)` raises when either `plan_overrides` or `preflight.extra_env` contains any `MERIDIAN_*` key. Fail-closed boundary on both channels (S046 and S046b). Spawn-side code in `src/meridian/lib/ops/spawn/execute.py` was updated so `plan_overrides` no longer carry `MERIDIAN_*` keys at the source.

**Why:** K5 fail-closed; preserves the invariant that the runtime channel is the sole producer of `MERIDIAN_*` child overrides. Silent filtering was rejected because a missing override is a silent behavior change, not a recoverable state.

### E6.3 — `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` stays on the plan-overrides channel for Phase 6

**What:** The E3.1 deferred consolidation (routing this env var through `preflight.extra_env`) was not completed in Phase 6. The env var remains on the plan-overrides channel with its existing routing preserved. Because `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` is not a `MERIDIAN_*` key, the fail-closed boundary does not reject it, and downstream behavior is unchanged.

**Why:** Moving the env var to `preflight.extra_env` without touching the surrounding preflight/plan-override callers is non-trivial and crosses Claude adapter-internal state that is easier to consolidate alongside Phase 7's projection/bootstrap convergence. Defer the rename to Phase 7 with no behavioral change in Phase 6.

**Addresses.** E3.1 (deferred, not resolved).

### E6.4 — Unit tester observations worth tracking (non-blocking)

- `merge_env_overrides(...)` preserves non-string values verbatim rather than rejecting or coercing. Today every call site passes strings, so this is a latent loose-schema issue, not a current defect.
- `LaunchContext` is declared frozen but can still be mutated with `object.__setattr__`. Python's frozen dataclass / Pydantic `frozen=True` only blocks normal attribute assignment; the C-API backdoor is not sealed. For Phase 6's contract this is acceptable because the `env` and `env_overrides` mapping views themselves are `MappingProxyType` (the real immutability boundary, per S054).

Both are flagged for the final review loop, not for an intra-phase fix.

### E6.5 — Smoke tester observations worth tracking (non-blocking)

- Parent allowlist duplicate entries (`A,A,B`) are deduped before launch on both runner paths. Parity holds (both paths behave identically), so S025 is verified. The contractual question of whether parent-env forwarded permission data counts as "user data subject to last-wins / no-dedupe" is deferred to the final review loop; today it is treated as adapter-internal resolver data.
- `CLAUDECODE` env var is scrubbed from child Claude launches on both paths. Scenario S025 text was stale (predated the scrub); the actual behavior is parity-preserving.

### E6.6 — Verifier observation (minor cleanup)

- `src/meridian/lib/harness/connections/claude_ws.py:51` still names the blocked-env set `_BLOCKED_CHILD_ENV_VARS`, a private module constant. It does not duplicate `constants.py` values (verified), but the naming is close enough to the shared constants that a future refactor should consider consolidating or at least renaming for audit clarity. Deferred to final review loop / Phase 7.

## E7 — Phase 7 execution decisions

### E7.1 — `HarnessBundle` registry is authoritative; dispatch is single runtime narrow

**What:** `src/meridian/lib/harness/bundle.py` now holds `HarnessBundle`, the bundle registry, and bootstrap-time validation (duplicate `HarnessId`, missing extractor, empty connection map, invalid transport key). `src/meridian/lib/streaming/spawn_manager.py` dispatches via `registry[harness_id]` plus one `isinstance(spec, bundle.spec_cls)` narrow. The flat connection registry in `src/meridian/lib/harness/connections/__init__.py` is retired; lookups delegate to the bundle registry.

**Why:** D1 plus D2 required a single authoritative paired registry with exactly one runtime narrow. Phase 7 is where those decisions land in code. No `if harness_id == ...` branches remain in the shared dispatch path.

### E7.2 — Eager bootstrap runs all drift guards at package import

**What:** `src/meridian/lib/harness/__init__.py` now has a load-bearing eager-import sequence plus `ensure_bootstrap()`. All five projection modules (`project_claude`, `project_codex_subprocess`, `project_codex_streaming`, `project_opencode_subprocess`, `project_opencode_streaming`) import the shared drift guard from `src/meridian/lib/harness/projections/_guards.py` and run it at module level. `_enforce_spawn_params_accounting()` is called as the last step of bootstrap. Fresh-interpreter import now exits 0 with three bundles registered and `_bootstrapped=True`.

**Why:** D5 + S030 + S039 require drift + accounting failures to surface at import time, not lazily at first spawn. An import-order cycle during early core module initialization forced the `ensure_bootstrap()` indirection — any caller that needs a ready registry can call it explicitly and the invariants are guaranteed before dispatch. S031 confirms no circular-import warnings from a fresh subprocess.

### E7.3 — Harness-owned extractors replace the streaming extractor shortcut

**What:** `src/meridian/lib/harness/extractors/{base,claude,codex,opencode}.py` now implement the `HarnessExtractor` protocol. `StreamingExtractor` routes through the bundle-owned extractor. `session_detection.py` uses bundle-first ownership inference. The legacy `extractor.py` is shrunk to a thin routing shim.

**Why:** The previous streaming extractor was a Claude-only shortcut that silently broke for Codex and OpenCode when the streaming path didn't carry a session id in its live events. Harness-owned extractors unify the fallback path with subprocess extractors, and the bundle registry makes the dispatch explicit.

### E7.4 — OpenCode XDG storage fallback (S049 fix)

**What:** OpenCode persists session state at `$XDG_DATA_HOME/opencode/storage/session_diff/<session_id>.json` (falling back to `~/.local/share/opencode/storage/...` when `XDG_DATA_HOME` is unset), not inside `child_cwd` or `state_root`. The original Phase 7 implementation assumed local artifacts and silently returned `None` for OpenCode. Fix coder p1485 added:

- `src/meridian/lib/harness/opencode_storage.py` — XDG-aware storage root resolution + session file iteration + direct session-id lookup.
- `src/meridian/lib/harness/extractors/opencode.py` — fallback path probes `$XDG_DATA_HOME/opencode/storage/{session_diff,session}`; selects candidate by payload `directory` hints, spawn-start-time window from `spawns.jsonl`, then latest mtime.
- `src/meridian/lib/harness/opencode.py` — implements `resolve_session_file(...)` so `meridian session log <spawn_id>` can open `ses_*.json` files.
- `tests/harness/test_extraction.py` and `tests/ops/test_session_log.py` — regression tests with temp `XDG_DATA_HOME` fixtures.

**Why:** S049 requires all three harnesses to recover session ids from on-disk artifacts and enable `meridian session log` end-to-end. OpenCode's global XDG storage is an integration reality that wasn't captured in the original design; treating it as an integration-boundary discovery rather than a design defect.

**Addresses.** S049 (verified after fix by smoke tester p1486).

### E7.5 — Unit tester tactical fixes for OpenCode MCP and exception hierarchy

**What:** During unit-test coverage (p1482), two small fixes landed to match scenario contracts:
- `project_opencode_streaming.py` now emits `mcp: {servers: [...]}` instead of a bare list, matching the real `opencode serve` POST /session schema observed during Phase 5 smoke probing.
- `HarnessCapabilityMismatch` on the OpenCode path now subclasses `ValueError` so reject-path tests can catch it via the `ValueError` supertype. Claude/Codex equivalents remain consistent.
- `_PROJECTED_FIELDS` is now exposed on all five projection modules so the import-time accounting checks are symmetric.

**Why:** Scenario S047 (mcp_tools projected to every harness) required the wire format to match the real `opencode serve` schema, not the placeholder Phase 5 shape. The exception base class change is a minor simplification; no call site was depending on the raw `HarnessCapabilityMismatch` type.

### E7.6 — S033 structural follow-up noted (non-blocking)

**What:** The verifier p1483 observed that Codex streaming and OpenCode streaming projections log "passthrough forwarding" but do not emit the managed-flag collision + last-wins shape that Claude's streaming projection uses. The scenario S033 contract is narrower ("DEBUG log for passthrough args"), which all three satisfy — so S033 is verified. The consistency gap across the three streaming log shapes is a structural follow-up for the final review loop or Phase 8 integration.

**Why:** Phase 7 is closed on the contract, not on the ideal. The refactor to unify debug-log shapes across streaming projections fits better alongside Phase 8's lifecycle convergence, where the same code paths will be touched.

### E7.7 — E3.1 `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` consolidation: still deferred

**What:** The long-running deferral from E3.1 (Phase 3) → E6.3 (Phase 6) was not consolidated in Phase 7. The env var remains on the plan-overrides channel with existing routing preserved.

**Why:** Phase 7 scope was bounded to bundle/dispatch/extractor convergence; moving the autocompact env var routing safely would expand into primary launch env plumbing beyond this phase's scope. The continued deferral is a conscious choice, not an oversight. Candidate home: final review loop or Phase 8 (primary launch env integration).

**Addresses.** E3.1 (deferred, still not resolved; flagged for final review).

## E8 — Phase 8: Runner, spawn-manager, and REST lifecycle convergence

### E8.1 — Resolver threading (S014)

`run_streaming_spawn(...)` now requires caller-supplied `perms: PermissionResolver`. The v1 `cast("PermissionResolver", None)` path and `UnsafeNoOpPermissionResolver(_suppress_warning=True)` escape hatch are removed. REST `/api/spawns` now threads the resolver through to the streaming runner unchanged. Identity-preserving invariant holds: `spec.permission_resolver is resolver`. This closes K3 (permission pipeline harness-agnostic) and K4 (no-arg `resolve_flags`) end-to-end.

### E8.2 — Structured missing-binary errors (S028)

`src/meridian/lib/harness/errors.py` defines shared `HarnessBinaryNotFound(Exception)` (non-frozen dataclass; frozen caused prior `FrozenInstanceError` regression). Both subprocess (`spawn_and_stream`) and streaming (`run_streaming_spawn`) now raise this same class with `harness_id`, `binary_name`, and `searched_path`. Smoke tester p1491 verified parity across all 6 matrix cells (3 harnesses × 2 runners).

### E8.3 — Idempotent cancel/interrupt (S041)

`send_cancel()` and `send_interrupt()` are idempotent across all four connection types. A second awaited call becomes a no-op, and exactly one `cancelled` terminal event is emitted per connection. Verified by unit tester p1490 with parametrized coverage.

### E8.4 — First terminal status wins (S048)

Spawn-store finalize semantics are idempotent: a second terminal write with a different status is now a no-op (not an exception). Race tests verify both orderings (cancel-first and completion-first). Both terminal attempts remain audit-visible in event logs; persisted terminal state is single-winner.

### E8.5 — S042 fix loop (p1504)

Smoke tester p1491 found `resolve_execution_terminal_state` could not yield `cancelled`; streaming-runner finalize persisted only `succeeded`/`failed` even when signal handling fired `send_cancel`. Fix coder p1504 added an explicit cancellation branch, threaded cancellation intent through finalize callsites in `streaming_runner`/`runner`/`process`, hardened `has_durable_report_completion` against cancelled-frame false positives (report extraction filters terminal control-frames), and prevented streaming cancellation from being overwritten by `missing_report`.

Decision: cancellation intent is threaded as an explicit resolver parameter rather than inferred from `failure_reason` strings. Explicit signaling is safer and more future-resistant.

### E8.6 — Lazy PID/heartbeat cleanup (S042 tertiary)

Smoke tester p1491 found `harness.pid` / `heartbeat` / `background.pid` persisted after terminal rows. Fix coder p1504 added `cleanup_terminal_artifacts` in `src/meridian/lib/state/spawn_store.py` and invoked it from `src/meridian/lib/ops/spawn/api.py` read paths (`meridian spawn show` and `meridian spawn list`).

Crash-only design is preserved by keeping cleanup on read/reconciliation paths (no write-path coupling). Scenario text mentioned `meridian status`, but that command does not exist; scenario contract allows `meridian status OR meridian spawn show`, so `spawn show`/`spawn list` wiring satisfies contract intent.

### E8.7 — S027 verifier concurrency race

Verifier p1489 ran while unit tester p1490 was still editing `tests/exec/test_signals.py`, observed a transient failing intermediate state, and marked S027 `failed`. Orchestrator direct reruns after edit stabilization produced full-suite parity (552/552) under normal and `PYTHONOPTIMIZE=1` modes.

Judgment call: S027 was re-verified via direct objective evidence (test counts), without re-spawning verifier; re-spawn would add no new information. Process note for future phases: sequence verifier only after all other testers complete to avoid test-file concurrency races.

### E8.8 — Subprocess variant of S042 skipped

All three harnesses currently declare `supports_bidirectional=True`, so `ops/spawn/execute.py` routes user-facing CLI spawns through `execute_with_streaming`. `execute_with_finalization` (subprocess runner) is unreachable from `meridian spawn`.

S042's subprocess-vs-streaming clause therefore degrades to streaming parity across harnesses at CLI layer. Subprocess library-entrypoint coverage remains in S028 direct `spawn_and_stream` tests. Accepted as design reality and recorded here instead of forcing a synthetic subprocess-wrapper test.

### E8.9 — Smoke re-verify independence skipped (judgment)

After p1504 reran the same smoke driver and produced post-fix evidence, the orchestrator did not respawn an independent `@smoke-tester` for S042 re-verify. Rationale: evidence is objective JSON rows in `spawns.jsonl`; an additional rerun would not provide new signal beyond validating the same artifact shape.

This follows v3 coordinator posture: strict on invariants, pragmatic on process overhead when evidence is objective.

## E9 — Phase 9: Final review fix pass (p1515 findings)

### E9.1 — F1 completion-task race: bounded terminal-event grace wins over synthetic drain success

`_run_streaming_attempt(...)` and `run_streaming_spawn(...)` now treat `completion_task` as non-authoritative when the terminal-event future is still pending. New helper `_await_terminal_outcome_after_completion(...)` waits a bounded 0.5s grace window for a queued terminal frame to be consumed.

Decision: when natural drain completion arrives first, we still give the subscriber a short chance to publish terminal semantics. If the terminal event arrives in-window, that outcome overrides `DrainOutcome(status="succeeded", exit_code=0)` from natural drain completion.

Why this closes the race: the previously unhandled `completion_task in done` branch could drop Claude `result` errors / OpenCode `session.error` frames. The new path records terminal status even when drain finished first.

Tradeoff: 0.5s adds a bounded tail-latency only on this race edge; normal terminal-event-first and signal/budget/timeout paths are unchanged.

### E9.2 — F2 late-signal race: terminal-observed precedence is end-to-end

Two precedence changes landed:
- wait-branch order now evaluates terminal-event completion before signal completion in both `run_streaming_spawn(...)` and `_run_streaming_attempt(...)`.
- `_AttemptRuntime` now carries `terminal_observed`, and `execute_with_streaming(...)` finalize suppresses cancellation inference from `received_signal` when terminal was already observed in the final attempt.

Decision: once a concrete harness terminal event is observed, a same-wakeup or later SIGINT/SIGTERM cannot downgrade final status to `cancelled`.

Why this closes the race: branch reordering alone was insufficient because outer finalize still inferred cancellation from remembered signal state. The `terminal_observed` flag threads precedence through finalization.

### E9.3 — F3 missing-binary diagnostics: preserve structured payload text through finalize

`execute_with_streaming(...)` no longer rewrites startup launch failures to the generic marker `"infrastructure_error"` when `_run_streaming_attempt(...)` returns `start_error`. It now persists the full `start_error` string.

Decision: carry launch-failure diagnostics through to the terminal row verbatim (at minimum), so `spawn show` preserves details like `binary_name` and `searched_path` from `HarnessBinaryNotFound`.

Why this closes the regression: users now see actionable missing-binary diagnostics in persisted spawn state instead of an unhelpful generic failure reason.

### E9.4 — H1 (p1518): extracted duplicated runner helpers into `launch/runner_helpers.py`

**What changed:** moved these six byte-identical helpers out of both runners into `src/meridian/lib/launch/runner_helpers.py`, then imported them from both `runner.py` and `streaming_runner.py`:

- `spawn_kind`
- `append_budget_exceeded_event`
- `guardrail_failure_text`
- `append_text_to_stderr_artifact`
- `artifact_is_zero_bytes`
- `write_structured_failure_artifact`

**Finding closed:** p1518 / H1.

**Tradeoff:** no behavioral change intended; this is a pure move that reduces duplicated maintenance surface and trims both runner modules.

### E9.5 — H2 (p1518): removed dead `extract_session_id_from_artifacts` alias

**What changed:** deleted `extract_session_id_from_artifacts(...)` from `src/meridian/lib/harness/common.py` and switched Claude call sites to `extract_session_id_from_artifacts_with_patterns(...)` directly (`src/meridian/lib/harness/claude.py`, `src/meridian/lib/harness/extractors/claude.py`). Updated exec tests that imported the alias.

**Finding closed:** p1518 / H2.

**Tradeoff:** none; alias was one-line passthrough and created duplicate API surface.

### E9.6 — M1 (p1518 + p1516): deduped extractor mapping scanner in base module

**What changed:** added `session_from_mapping_with_keys(payload, keys)` to `src/meridian/lib/harness/extractors/base.py` and rewired Claude/Codex/OpenCode event extraction to pass harness-specific key tuples.

**Finding closed:** p1518 / M1.

**Tradeoff:** key selection remains harness-local data; recursion logic is centralized.

### E9.7 — M4 (p1518): codex adapter extract methods are still production-coupled

**What changed:** verified callers in `src/meridian` and kept `CodexAdapter.extract_session_id(...)` / `CodexAdapter.extract_report(...)` in place.

**Why kept:** subprocess/primary flows still call adapter-level extraction via `SubprocessHarness` paths, including:

- `src/meridian/lib/launch/process.py` (`extract_latest_session_id(extractor=plan.adapter, ...)`)
- `src/meridian/lib/launch/runner.py` (`enrich_finalize(extractor=harness, ...)`, `extract_latest_session_id(extractor=harness, ...)`)

**Finding status:** p1518 / M4 closed by verification; deletion deferred because coupling is still live in production code paths.

### E9.8 — Types M-1 + M-2 (p1516): codex contract alignment

**What changed:**

- `HarnessCapabilityMismatch` in `project_codex_subprocess.py` now subclasses `ValueError` (OpenCode parity).
- codex tool-flag stripping now logs dropped `--allowedTools` tokens in addition to existing `--disallowedTools` warning.

**Findings closed:** p1516 / M-1 and M-2.

**Tradeoff:** keep drop behavior (Codex cannot enforce `--allowedTools`), but make downgrade observable.

### E9.9 — Types M-3 (p1516): hardened external registry mutability

**What changed:** `get_bundle_registry()` now returns `MappingProxyType(_REGISTRY)` and `_REGISTRY` is removed from `bundle.__all__`.

**Finding closed:** p1516 / M-3.

**Tradeoff:** internal registration remains mutable through `register_harness_bundle(...)`; external callers lose direct mutation access.

### E9.10 — Design M-3 (p1517): narrowed bootstrap retry ImportError suppression

**What changed:** `src/meridian/lib/harness/__init__.py` retry path now only swallows `ImportError` if `_is_expected_partial_init(...)` returns true; unexpected retry `ImportError` is re-raised.

**Finding closed:** p1517 / Design M-3.

**Tradeoff:** stricter startup failure behavior in exchange for preserving K9 drift-guard visibility.

### E9.11 — Final-review deferrals accepted for v3

- **D19 / C1 / Design M-1 — D19 budget breach accepted for v3.** `runner.py` and `streaming_runner.py` still exceed the 500-line target after helper extraction. Full L11 decomposition is deferred to a follow-up work item because: (a) decomposition is a pure refactor with no behavior change, (b) runtime correctness fixes in this review loop had priority, (c) clean split requires design-level phaseing not present in v3. Follow-up should open with: *split `runner.py` and `streaming_runner.py` into <=500 line units along finalize/retry/event-pump axes*.
- **Design M-2 — Dual adapter registry accepted for v3.** `HarnessRegistry` and bundle registry both retain adapter references. Not a current correctness bug because adapters are effectively stateless; defer unification to a follow-up that routes adapter lookup through `get_harness_bundle(harness_id).adapter`.
- **L-4 — `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` consolidation deferred.** Marked "won't fix in v3"; both routing channels are idempotent and functionally equivalent.
- **L-5 — S033 log-shape inconsistency deferred.** Contract passes as written; managed-flag collision detection remains Claude-specific for now.
- **L-6 — dead `except AttributeError` in `context.py` deferred.** Defensive branch appears unreachable with `BaseHarnessAdapter.preflight` default, but cleanup is postponed.
- **L-7 — `TransportId.SUBPROCESS` unused deferred.** Enum value remains aspirational and non-harmful.
- **L-8 — S042 narrowing recorded.** Scenario notes now explicitly state user flow reaches streaming only; subprocess variant remains library-level coverage. Scenario result status is unchanged.

### E9.12 — Residual F2 same-wakeup race: completion branch now gates signal cancellation

Residual race from p1521: when `completion_task` and `signal_task` were both ready in the same `asyncio.wait(...)` wakeup but `terminal_event_future` was still pending, `_run_streaming_attempt(...)` and `run_streaming_spawn(...)` took the signal branch first. That skipped the bounded completion-grace helper and could overwrite an already-emitted terminal frame as `cancelled`.

Decision: branch priority is now `terminal_event_future` -> `completion_task` -> `signal_task` (and then other stop conditions). Inside the completion branch, we always run `_await_terminal_outcome_after_completion(...)` first. If grace observes a terminal outcome, it wins; if grace times out, pending signal cancellation is honored.

Coverage: added `test_execute_with_streaming_completion_grace_on_same_wakeup_signal`, which forces `wait_for_completion(...)` to set SIGTERM at completion return time while terminal future resolution is delayed into the grace window. Assertion verifies final row stays terminal-success (`succeeded`, exit `0`) rather than `cancelled`.

F3 cosmetic structured-field extension (`binary_name`, `searched_path` on persisted rows) was not included in this pass; user-visible diagnostics remain functional via `error` text.

### E9.13 — Final convergence: v3 declared closed

Round 3 runtime re-re-reviewer (p1525) confirmed that the residual same-wakeup F2 race documented in E9.12 is now fully closed. No new findings were introduced by the fix. Static review of `streaming_runner.py` verified:

- `run_streaming_spawn(...)` and `_run_streaming_attempt(...)` both evaluate terminal-event completion first, completion-task second, signal-task third.
- Every completion branch unconditionally runs `_await_terminal_outcome_after_completion(...)` before honoring pending signal cancellation.
- `execute_with_streaming(...)` finalize computes `cancelled` only when `not final_attempt_terminal_observed`, so late SIGTERM cannot downgrade an already-observed terminal outcome.
- The new regression test `test_execute_with_streaming_completion_grace_on_same_wakeup_signal` (added in p1524) exercises the exact interleaving the race depended on and asserts persisted `succeeded` rather than `cancelled`.

F2 was the last non-trivial finding across the final review loop. All other lane findings (runtime F1/F3, types M1–M4, refactor H1/H2/M1/M3/M4, design M-1/M-2/M-3 and lows L-4 through L-8) were either closed in earlier E9.x entries (E9.1 – E9.10) or explicitly deferred with follow-up hooks (E9.11).

**Final gate results** (orchestrator-run on `db7eb89`, post all fix commits):

- `uv run ruff check .` → All checks passed
- `uv run pyright` → 0 errors, 0 warnings, 0 informations
- `uv run pytest tests/ --ignore=tests/smoke -q` → 563 passed
- `PYTHONOPTIMIZE=1 uv run pytest tests/ --ignore=tests/smoke -q` → 563 passed (pytest `-O` warning only)

**Convergence declaration.** v3 is converged. All eight implementation phases are committed, all K1–K9 invariants are live in code, all seven Phase 8 scenarios are verified, all four gates are green, and every finding from the final review loop is either closed or recorded as a deferred follow-up with a concrete next-work-item hook. The work item is ready to close; see `run-report.md` for the consolidated audit trail and the Follow-ups section there for the next-cycle pickup list.

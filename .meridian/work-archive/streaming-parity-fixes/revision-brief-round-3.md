# Revision Round 3 — Reframe: Meridian is a Coordinator, Not a Policy Engine

## Purpose

Three independent reviewers (opus p1433, gpt-5.2 p1435, gpt-5.4 p1434) audited the v2 design for SOLID / extensibility / missing invariants and converged on a clear picture: v2 has both real internal-consistency gaps AND overreach where meridian tries to police user or harness behavior. This revision separates the two.

## The Reframe

**Meridian is a coordinator, not a policy engine.** It:

- Launches harnesses and forwards configuration to them
- Captures events they emit
- Manages spawn lifecycle (start, stop, wait, inject, cancel)
- Persists state (spawns.jsonl, sessions.jsonl, output.jsonl)

It does NOT:

- Execute tool calls
- Enforce sandboxes
- Validate what harnesses decide is allowed
- Second-guess what users want to pass through

**The core principle:** every strict check must answer "does this protect against meridian's own internal drift?" If the answer is "no, it's policing user or harness behavior," drop it.

Strict checks for **developer drift**, forgiving for **user/harness data**.

## Corrections to Drop (Overreach)

### D1. Delete all reserved-flag machinery

`_RESERVED_CODEX_ARGS`, `_RESERVED_CLAUDE_ARGS`, `strip_reserved_passthrough`, the opus-proposed heuristic regex backstop `/--(sandbox|approval|...)/i`, and the opus-proposed probe-derived flag inventory from `codex app-server --help`. ALL of it.

**Rationale:** `extra_args` is true passthrough. If a user passes `-c sandbox_mode=yolo`, that's between them and Codex. Meridian isn't the security gate — the harness is. The user could invoke Codex directly. The only thing stripping accomplishes is silently confusing users when their flag disappears.

**What remains:** `extra_args` is forwarded verbatim to each transport. Document in the design that permission intent is normally expressed via `PermissionConfig`, but users taking manual control via `extra_args` is a supported escape hatch (not a security boundary).

### D2. Delete the PermissionConfig coherence validator

Don't add a `@model_validator` that rejects `approval=confirm + sandbox=yolo` or similar. If the harness accepts the combo, meridian accepts it too.

**Rationale:** meridian is not the authority on which permission combinations make semantic sense. That's the harness's decision. A combination that looks weird today may be meaningful tomorrow.

### D3. Delete the MCP forbidden-prefix guard

`_FORBIDDEN_FIELD_PREFIXES = frozenset({"mcp_"})` as a special import-time check. No.

**Rationale:** enforcement against a specific string prefix is hacky. If someone's adding MCP support, they know what they're doing. And the existing projection drift guard already catches "field with no consumer."

### D4. Restore mcp_tools to SpawnParams

v2 D23 deleted `mcp_tools`. That was wrong. Restore it as a first-class forwarded field:

- `SpawnParams.mcp_tools: tuple[str, ...]` (or similar)
- Each adapter's `resolve_launch_spec` includes it on its spec subclass
- Each projection maps it to the transport-specific wire format (Claude `--mcp-config`, Codex `-c mcp.servers.X.command=...`, OpenCode HTTP session payload `mcp` field)
- The projection drift guard counts it as a normal field — no special handling

Explicit design note: "MCP auto-packaging through mars is a separate work item (not in v2 scope). Manual MCP configuration via SpawnParams works today — users can point at tools they've set up themselves."

### D5. Loosen PermissionConfig Literals

If Claude or Codex adds a new sandbox tier tomorrow, meridian shouldn't need a source change to forward it. Consider relaxing the Literals to `str` with documentation of known values, or keep the Literals but add a clear path for extension.

## Corrections to Keep (Real Internal Consistency)

These are genuine gaps. Revision round 3 should codify them as invariants in the design docs, with concrete enforcement mechanisms.

### K1. Transport dispatch keyed on `(harness, transport)`

**Finding:** gpt-5.4 HIGH. Bundle is keyed only by harness_id and carries exactly one connection_cls. Adding Claude-over-HTTP in the future requires rewiring shared bundle/dispatch — Open/Closed failure at the transport boundary.

**Options:**
(a) Generalize bundle to `HarnessBundle[SpecT, ConnectionT]` with dispatch on `(harness_id, transport_id)`, allowing multiple connections per harness.
(b) Accept the closure deliberately — one harness, one connection. Document why (YAGNI, current harnesses don't need it) and add a decision entry.

Pick one. If (a), update typed-harness.md, bundle.py, dispatch site, and all diagrams. If (b), add a decision with rationale.

### K2. Bundle registry uniqueness with `register()` helper

**Finding:** opus HIGH, gpt-5.2 MEDIUM. `_REGISTRY: dict[str, HarnessBundle] = {}` has no duplicate guard. Last-import-wins silently changes dispatch.

**Fix:** Add `register_harness_bundle(bundle)` as the only mutation site. Raise `ValueError` on duplicate. Add eager import in `harness/__init__.py` to guarantee all bundles register before the first dispatch. Unit test asserting duplicate registration fails.

### K3. Protocol/ABC method-set reconciliation

**Finding:** opus MEDIUM. `HarnessAdapter` Protocol requires `id`, `resolve_launch_spec`, `preflight`. `BaseSubprocessHarness` ABC only marks `resolve_launch_spec` abstract. A subclass missing `id` is ABC-instantiable but Protocol-noncompliant, crashes deep in dispatch with `AttributeError`.

**Fix:** Add `id` as `@abstractmethod` on `BaseSubprocessHarness`. Unit test reconciling Protocol attributes vs ABC abstractmethods.

### K4. HarnessId branching backdoor in PermissionResolver

**Finding:** opus HIGH. `PermissionResolver.resolve_flags(self, harness: HarnessId)` invites consumers to `if harness == CLAUDE` inside the resolver — re-introducing the harness-id branching that `adapter.preflight()` was meant to eliminate.

**Fix:** Two options.
(a) Drop the `harness` parameter entirely — return harness-agnostic policy, projections translate to wire format.
(b) Keep the parameter but add an invariant in permission-pipeline.md forbidding resolver-side harness branching.

(a) is cleaner. Pick one with reasoning.

### K5. MERIDIAN_DEPTH sole-producer invariant

**Finding:** opus MEDIUM, gpt-5.2 HIGH. `prepare_launch_context` merges `plan.env_overrides` + `runtime_overrides` + `preflight.extra_env`. No doc enforces "only `RuntimeContext.child_context()` writes MERIDIAN_DEPTH."

**Fix:** Add invariant in runner-shared-core.md: only `RuntimeContext.child_context()` (or an equivalently-documented helper) may produce MERIDIAN_* runtime context overrides. `preflight.extra_env` may add harness-specific variables but must not override any MERIDIAN_* key. Enforce with an assertion in the merge helper and a unit test.

### K6. Session ID extraction parity (p1385 gap)

**Finding:** opus HIGH, gpt-5.2 HIGH. p1385 explicitly flagged that `StreamingExtractor` doesn't support harness-specific fallback session detection (Claude project files, Codex rollout files, OpenCode logs). Subprocess has it. v2 doesn't address it.

**Options:**
(a) Pull into v2: add HarnessExtractor[SpecT] to the bundle, with required session_id detection + artifact fallback. Add import-time extractor drift guard.
(b) Explicitly defer: add to overview.md §Scope as out-of-scope with a tracker.

Prefer (a) if the design can absorb it without blowing scope. Otherwise defer explicitly.

### K7. Spec / config immutability coverage

**Finding:** opus MEDIUM, gpt-5.2 HIGH. `ResolvedLaunchSpec` is frozen. `PermissionConfig` is not. `PreflightResult.extra_env: dict` is mutable-inside-frozen-dataclass. `LaunchContext.env` / `env_overrides` same.

**Fix:** Add `model_config = ConfigDict(frozen=True)` to `PermissionConfig`. Wrap dict fields with `MappingProxyType` at construction. Test asserting mutation raises.

**Important:** this is about internal state integrity (meridian's own coordination logic depends on stable values). NOT about validating the values themselves.

### K8. Cancel / interrupt / SIGTERM parity

**Finding:** opus MEDIUM, gpt-5.2 HIGH. `HarnessConnection` has `send_interrupt` / `send_cancel` / `stop` but no doc specifies idempotency, transport-neutral signal handling, or user-observable parity.

**Fix:** Add a semantics table to typed-harness.md §"Connection Contract":

- `send_cancel` and `send_interrupt` are idempotent and converge to a single terminal spawn status
- Runner SIGTERM/SIGINT handling is transport-neutral: propagate intent to the harness, persist a cancellation event, rely on crash-only reconciliation for cleanup
- Define exactly-once semantics for cancellation event emission and ordering relative to error emission

Add scenarios for cancel/interrupt parity across subprocess and streaming.

### K9. Per-adapter handled-fields guard

**Finding:** gpt-5.4 MEDIUM. `_SPEC_HANDLED_FIELDS` only proves "every SpawnParams field has a home somewhere," not "each adapter maps it." A new field can silently noop on one harness.

**Fix:** Add per-adapter handled-fields set that must union to `SpawnParams.model_fields`. Fails at import time if any adapter leaves a field unclaimed.

## Corrections to Clarify

### C1. LaunchContext parity claim

Currently too strong — `env` depends on ambient `os.environ` and isn't testable. Narrow the claim to the deterministic subset: `run_params`, `spec`, `child_cwd`, and `env_overrides` plus derived `MERIDIAN_*` fields.

### C2. Projection module import bootstrapping

Import-time drift guards only help if the module is imported. Add a note that `harness/__init__.py` (or a central `projections/__init__.py`) imports all projection modules eagerly so guards always execute.

### C3. `project_codex_streaming.py` line budget

Not a fix, just a marker. Add D19-style "if this file exceeds 400 lines, split into `project_codex_streaming_appserver.py` + `project_codex_streaming_rpc.py`."

## Source Material for Reviewers

- opus SOLID audit: .meridian/spawns/p1433/report.md
- gpt-5.2 missing invariants: .meridian/spawns/p1435/report.md
- gpt-5.4 extensibility: .meridian/spawns/p1434/report.md
- v2 design: .meridian/work/streaming-parity-fixes/design/
- v2 decisions: .meridian/work/streaming-parity-fixes/decisions.md

## Deliverables

1. Updated design docs (7 files under design/) with the reframe applied
2. Restored `mcp_tools` as a first-class field with projection mapping
3. Removed reserved-flag machinery, PermissionConfig validator, MCP forbidden-prefix guard
4. Codified the 9 keeper invariants (K1-K9) with concrete enforcement mechanisms
5. Revision ledger entries H1-H? in decisions.md documenting the round 3 changes
6. Updated scenarios/ for any new invariants introduced (e.g., bundle registry uniqueness, cancel idempotency)
7. Updated overview.md §Scope with session ID extraction decision (pull in or explicit defer)

## What NOT to Do

- Don't add any machinery that polices user input or harness behavior
- Don't add any validators that reject combinations that "look weird"
- Don't add any special-case guards against specific string prefixes or flag names
- Don't refuse to launch a spawn because the user gave meridian something unexpected — forward to the harness


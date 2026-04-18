# R06 Redesign — Design-Alignment Convergence Review

You are reviewing the **redesigned R06 package** that converts the launch
subsystem from a hexagonal *shell* into a typed pipeline owned by one
factory. This is a final convergence review on the design package only —
not on implementation.

## Scope

The previous R06 implementation produced a hexagonal shell:
`build_launch_context()` exists and `LaunchContext` is a sum type, but
composition still lives in driving adapters because the factory's input
DTO (`PreparedSpawnPlan.ExecutionPolicy`) carries already-resolved
`PermissionConfig` + live `PermissionResolver`. Four convergent reviewer
reports (design-alignment, correctness, structural, library-research)
called for an honest redesign.

The redesign:
- Replaces the `PreparedSpawnPlan` factory boundary with raw `SpawnRequest`
  (currently a dead abstraction at `harness/adapter.py:150`).
- Makes the factory a typed pipeline of named single-owner stages
  (`resolve_policies`, `resolve_permission_pipeline`, `compose_prompt`,
  `build_resolved_run_inputs`, `materialize_fork`, `project_launch_command`,
  `build_env_plan`).
- Enforces fork-after-row in every driver and reduces orphan-fork window
  to "spawn row marked failed with documented reason".
- Wires `observe_session_id()` per adapter; deletes `launch/session_ids.py`.
- Moves permission-flag projection out of the port contract module
  (`harness/adapter.py`) into each driven adapter.
- Replaces `scripts/check-launch-invariants.sh` (rg-count gaming surface)
  with a triad: behavioral factory tests + CI reviewer drift gate +
  pyright/ruff/pytest.

## What to read (in this order)

1. `decisions.md` D17 (prior R06 decision) and D19 (this redesign).
2. `design/refactors.md` R06 section (lines 137–656) — the full agenda.
3. `design/architecture/launch-core.md` — A06, the observational
   architecture leaf for the launch domain core.
4. `design/architecture/overview.md` — A06 added to TOC and Reading Order.
5. `design/architecture/harness-integration.md` — A04, the workspace
   projection that depends on A06.
6. `design/feasibility.md` FV-11 (raw-`SpawnRequest` factory boundary
   viable) and FV-12 (reviewer-as-drift-gate fits CI loop).
7. `reviews/r06-retry-correctness.md` and `reviews/r06-retry-structural.md`
   — the two reviews that drove the redesign. Verify the redesign
   addresses each finding.

## Focus areas

### 1. Design alignment

Does the redesigned R06 actually deliver what `decisions.md` D17 (and now
D19) committed to? Specifically:

- **Centralization**: composition lives only in `build_launch_context()`
  and its named pipeline stages. No driving adapter calls
  `resolve_policies`, `resolve_permission_pipeline`,
  `adapter.resolve_launch_spec`, `adapter.build_command`, or
  `adapter.fork_session` directly.
- **Single owners**: bypass dispatch (one place), fork materialization
  (one place), `MERIDIAN_HARNESS_COMMAND` parsing (one place),
  `TieredPermissionResolver` construction (one place),
  `RuntimeContext` type (one place).
- **Sum-type discipline**: `LaunchContext` dispatch uses exhaustive
  `match` + `assert_never`, not `isinstance`.
- **Persisted-artifact serializability**: worker `prepare → execute`
  artifact is plain JSON; no `arbitrary_types_allowed`; no live objects.

Verify: A06 (`launch-core.md`) is consistent with R06 (`refactors.md`).
Anywhere they diverge is a finding.

### 2. Coherence with the rest of the design package

- Does A06 fit cleanly with A04 (harness-integration)? A04 specifies the
  `project_workspace()` adapter seam; A06 specifies the factory that
  hosts it. Verify the seam is reachable and the contract A04 describes
  is implementable inside the A06 pipeline.
- Does the redesign preserve user-visible behavior described in spec
  leaves (`design/spec/`)? R06 is structural; spec leaves should not
  need updates. Flag any spec leaf that does need an update.
- Does `decisions.md` D19 capture the full rationale, including why
  alternatives were rejected (keep PreparedSpawnPlan with renames; adopt
  a DI container library; AST-based stricter rg checks)?

### 3. Verification triad soundness

The redesign deletes `scripts/check-launch-invariants.sh` and replaces it
with three layers:

1. Behavioral factory tests (10 enumerated tests).
2. CI-spawned `@reviewer` architectural drift gate against
   `.meridian/invariants/launch-composition-invariant.md`.
3. pyright + ruff + pytest as the correctness gate.

Evaluate:
- Are the 10 enumerated behavioral tests actually load-bearing? Are any
  missing for the load-bearing invariants (single-owner constraints,
  fork-after-row, dry-run/runtime parity, persisted-artifact shape)?
- Is the invariant-prompt content for the drift gate concrete enough?
  Could a future reviewer read it and rule on a diff without ambiguity?
- Does the triad close all 14 evasion patterns the structural review
  enumerated for the rg-count script?

### 4. Closes prior reviewer findings

Walk each finding in `reviews/r06-retry-correctness.md` and
`reviews/r06-retry-structural.md` and verify the redesign closes it. If
any finding is preserved as out-of-scope, verify it's logged with a
follow-up pointer (e.g., issue #34, issue #32, or `decisions.md`
out-of-scope).

### 5. Risks the redesign may introduce

The redesign is large. Look for:
- Stages that the agenda implies but doesn't name an owner for.
- Cross-cutting concerns the pipeline ordering could break (e.g.,
  preflight running inside bypass for dry-run/runtime parity — verify
  this is consistent with A04's preflight contract).
- Hidden coupling between adapters and the factory that could leak back
  into composition (e.g., adapter callbacks during pipeline execution).
- Any "natural place to put X" without an explicit owner in the
  single-owner table.

## Output format

Write `reviews/r06-redesign-alignment.md` with sections:

```
# R06 Redesign — Design-Alignment Convergence Review

## Verdict
{pass | shape-change-needed | block}

## Critical findings
(only if verdict is not "pass")

## Major findings

## Minor findings / nits

## What converges cleanly
(brief — what the redesign does well; helps the orchestrator know what to
preserve under any further iteration)

## Severity count
- blocker: N
- major: N
- minor: N
```

For each finding, give: pointer (file:line or section ref), what's wrong,
why it matters, fix sketch (sentence or two).

## Constraints

- Stay at design altitude. If a finding is implementation-level
  ("the function should be named X"), downgrade or skip.
- Do not propose alternative architectures unless the redesign has a
  load-bearing flaw. The frame (3 driving adapters, 1 factory, 2
  executors, 3 driven adapters, sum-type `LaunchContext`) is settled.
- The previous R06 reviews already established structural debt; do not
  re-derive their findings, but do verify the redesign closes them.
- Read-only: write only to `reviews/r06-redesign-alignment.md`.

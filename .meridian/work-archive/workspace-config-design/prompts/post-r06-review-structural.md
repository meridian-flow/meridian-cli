# Post-R06 Review — Structural / Refactor Soundness

## Context

R06 (hexagonal launch core) was shipped by spawn `p1900` across 6 commits on main (`3f8ad4c`..`efad4c0`). The orchestrator did all work inline with no subagent review or testing. You're the refactor-soundness reviewer.

Your lane: **is the new structure clean, or did the refactor leave tangled code?** Not "does it work" (correctness reviewer). Not "does it match the design" (design-alignment reviewer). You look for:

- Tangled dependencies between modules that should be separate.
- Mixed concerns in a single file/function.
- Premature abstractions or abstractions with leaky seams.
- Coupling that will compound into drift during R05.
- Code smells: god objects, long parameter lists, deep call chains, duplicated logic, dead code.

## Read first

- `git diff bb72a85..efad4c0 -- src/` — the R06 diff.
- `.meridian/spawns/p1900/report.md` — claimed deliverables including deviations I04, I05, I06.
- `.meridian/work/workspace-config-design/design/refactors.md` R06 — target architecture.

## Review lanes

### 1. Pipeline stage boundaries

Per R06, `build_launch_context()` should orchestrate a pipeline of one-builder-per-concern stages. Verify:

- Each stage lives in its own module (`launch/policies.py`, `launch/permissions.py`, `launch/fork.py`, `launch/env.py`).
- Stages communicate only through typed data — no shared mutable state.
- No stage reaches into another stage's internals.
- `build_launch_context()` is thin orchestration, not a second place composition happens.

Check the stages for creep: are `policies.py`, `permissions.py`, `fork.py` actually minimal, or did they absorb unrelated logic?

### 2. Driving-adapter rewiring

Three driving adapters now call `build_launch_context()`. Verify each:

- **Primary** (`launch/plan.py`, `launch/process.py`): does it still carry composition logic itself, or did it cleanly delegate?
- **Worker** (`ops/spawn/execute.py`, `ops/spawn/prepare.py`, specifically `build_create_payload`): deviation I04 says `resolve_policies` is still called from driving adapters. Is this actually a pre-composition step, or did composition leak out of the factory?
- **App streaming HTTP** (`app/server.py`): deviation I05 says `TieredPermissionResolver` is constructed in `server.py` for HTTP input validation. Is the boundary honest, or is this composition dressed as validation?

For each deviation I04/I05, ask: does this leave the factory still being the sole composition point, or does it erode the invariant?

### 3. `LaunchContext` sum type + executor dispatch

`LaunchContext = NormalLaunchContext | BypassLaunchContext`. Executors use `match` + `assert_never`. Verify:

- The sum type actually enforces exhaustiveness — no `cast(Any, ...)` or `isinstance` ladders bypassing it.
- Every field on `NormalLaunchContext` is genuinely required (not `Optional` with default `None`).
- Bypass carries only what bypass needs.
- Deviation I06 (duplicate `LaunchResult` in `types.py` vs `context.py`) — are the two types genuinely different concepts, or is this a naming collision that'll cause confusion?

### 4. Type split: `SpawnRequest` / `SpawnParams`

Per design: `SpawnRequest` is user-facing, `SpawnParams` is resolved. Verify:

- Driving adapters see `SpawnRequest`, not `SpawnParams`.
- Only factory + post-factory code sees `SpawnParams`.
- Fields are cleanly partitioned — no "raw" fields leaking into `SpawnParams`, no "resolved" fields on `SpawnRequest`.
- Call graph: who constructs `SpawnParams` today? If it's constructed anywhere outside the factory (or factory helpers), the split is incomplete.

### 5. `observe_session_id()` adapter seam

New method on harness adapter protocol. Verify:

- Method signature is clean (not leaking executor-specific details).
- Implementation is co-located with harness-specific code (per-harness module).
- Domain core doesn't know how session-ID is observed — it just calls the method.
- Old session-ID extraction code is actually removed from executors (not left as dead code).

### 6. Deletions + dead code check

`run_streaming_spawn` deleted, `SpawnManager.start_spawn` fallback removed. Verify:

- Every caller of the deleted code was also updated.
- No leftover imports, type hints, or commented-out code referencing deleted symbols.
- `prepare_launch_context()` was removed per the p1900 report — verify completely gone, not just stubbed.

### 7. CI invariants script

`scripts/check-launch-invariants.sh` runs `rg` patterns. Verify:

- Script is actually correct bash (not just exit 0 on errors).
- Patterns match the design's exit criteria precisely (definition-anchored + sole-caller).
- CI workflow hook (`.github/workflows/meridian-ci.yml`) actually runs the script as a required gate, not a non-blocking step.
- Escape hatch: is there a `|| true` or similar that defeats the check?

### 8. Import graph

Per D17: "Domain core imports from `harness/adapter.py` only — no imports of `harness/claude`, `harness/codex`, `harness/opencode`, `harness/projections`." Verify:

- `rg "from meridian.lib.harness\.(claude|codex|opencode|projections)" src/meridian/lib/launch/` → 0 matches.
- Adjacent check: does `src/meridian/lib/ops/spawn/` cleanly separate from `src/meridian/lib/launch/`? Any cross-pollination that will complicate R05?

### 9. R05 readiness

R05 will insert `project_workspace()` as a pipeline stage inside `build_launch_context()`. From a refactor-health angle:

- Is there exactly one place where R05 will insert? Or will R05 have to edit multiple files?
- Is the pipeline order clearly documented in code or just by convention?
- Is the adapter protocol stable enough that adding one more method won't cascade changes?

## Deliverable

Under 700 words:

- Findings as **Blocker / Major / Minor** with file:line references.
- Focus on structural health and future-proofing, not behavior.
- Name each **code smell** concretely; don't say "this is coupled" without pointing at the specific dependency.
- End with a **Verdict**: `clean-refactor` / `minor-structural-debt` / `refactor-health-concerns`.
- Do NOT modify code. Report only.

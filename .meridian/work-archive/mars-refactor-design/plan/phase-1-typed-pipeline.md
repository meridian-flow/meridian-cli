# Phase 1: A1 — Typed Pipeline Phases

**Round:** 1 (parallel with Phase 2)
**Risk:** High — restructures the core sync pipeline
**Estimated delta:** ~+200 LOC (new structs), ~-50 LOC (simplified execute)
**Codebase:** `/home/jimyao/gitrepos/mars-agents/`

## Scope

Decompose `sync::execute()` (lines 71-240 in `src/sync/mod.rs`) from a single 170-line function with 17 numbered steps into explicit phase functions with typed handoff structs. The function becomes a linear chain of phase calls. No behavioral change — the pipeline does the same thing, just structured differently.

## Why This Matters

Every subsequent phase (A2, A4, A5, B3, B4) needs to insert into or modify specific pipeline stages. Without typed phases, each change grows the monolithic function. This is the foundation.

## Files to Modify

| File | Changes |
|------|---------|
| `src/sync/mod.rs` | Define phase structs (`LoadedConfig`, `ResolvedState`, `TargetedState`, `PlannedState`, `AppliedState`). Extract phase functions (`load_config`, `resolve_graph`, `build_target`, `create_plan`, `apply_plan`, `finalize`). Rewrite `execute()` as orchestrator calling phase functions. |
| `src/sync/target.rs` | Move target-building logic into `build_target()` phase function (or keep as helper called by it). |
| `src/sync/plan.rs` | Move plan creation into `create_plan()` phase function (or keep as helper). |
| `src/sync/apply.rs` | Adapt to receive `PlannedState` instead of individual arguments. |
| `src/sync/diff.rs` | Adapt to be called from `create_plan()` with `TargetedState`. |
| `src/sync/mutation.rs` | May need minor signature changes if config mutation moves into `load_config()`. |

## Design Reference

Phase structs from `design/pipeline-decomposition.md` § A1:

```rust
/// Phase 1: Load and validate configuration under sync lock.
pub struct LoadedConfig {
    pub config: Config,
    pub local: LocalConfig,
    pub effective: EffectiveConfig,
    pub old_lock: LockFile,
    pub dependency_changes: Vec<DependencyUpsertChange>,
    pub _sync_lock: FileLock,
}

/// Phase 2: Resolved dependency graph.
pub struct ResolvedState {
    pub loaded: LoadedConfig,
    pub graph: ResolvedGraph,
    // model_aliases added later in Phase 6 (B4)
}

/// Phase 3: Desired target state after discovery + filtering.
pub struct TargetedState {
    pub resolved: ResolvedState,
    pub target: TargetState,
    pub renames: Vec<RenameAction>,
    pub warnings: Vec<ValidationWarning>,
}

/// Phase 4: Diff + plan ready for execution.
pub struct PlannedState {
    pub targeted: TargetedState,
    pub plan: SyncPlan,
}

/// Phase 5: Applied results.
pub struct AppliedState {
    pub planned: PlannedState,
    pub applied: ApplyResult,
}
```

Phase functions consume prior state by value (D7 — move semantics, no cloning):

```rust
pub fn execute(ctx: &MarsContext, request: &SyncRequest) -> Result<SyncReport, MarsError> {
    validate_request(request)?;
    let loaded = load_config(ctx, request)?;
    let resolved = resolve_graph(ctx, loaded, request)?;
    let targeted = build_target(ctx, resolved, request)?;
    let planned = create_plan(ctx, targeted, request)?;
    if request.options.frozen { check_frozen_gate(&planned)?; }
    let applied = apply_plan(ctx, planned, request)?;
    let report = finalize(ctx, applied, request)?;
    Ok(report)
}
```

## Step-by-Step Mapping

Map current execute() steps to phase functions:

| Current Steps | Phase Function | What Moves |
|---------------|----------------|------------|
| 1-4b: lock, config load, mutation, local config merge | `load_config()` | Acquire sync lock, load mars.toml, apply ConfigMutation, load mars.local.toml, merge into EffectiveConfig |
| 5-7: validate targets, load lock, resolve graph | `resolve_graph()` | Validate upgrade targets exist, load mars.lock, resolve dependency graph |
| 8-11: build target, collisions, rewrites, validation | `build_target()` | Build TargetState from graph, detect collisions, rewrite skill references, validate |
| 12-13c: diff, plan, _self injection | `create_plan()` | Compute diff, create SyncPlan. NOTE: _self injection stays here for now — Phase 3 (A2) will move it into build_target |
| 14: frozen gate | `check_frozen_gate()` | Standalone check between plan and apply |
| 15-16: persist config, apply plan | `apply_plan()` | Write config if mutated, apply plan to disk |
| 17: write lock | `finalize()` | Build new lock, write it, construct SyncReport |

## Constraints

- **Keep _self injection in place for now.** Phase 3 (A2) will move it into `build_target()`. For this phase, `inject_self_items()` stays as a call within `create_plan()`. Don't try to fix it here — that's Phase 3's job.
- **Phase structs nest by ownership** (D3). `ResolvedState` owns `LoadedConfig`. This means `finalize()` can access `loaded.old_lock` through the nesting chain.
- **ctx and request are borrowed** — they're read-only context shared across all phases.
- **No model_aliases field on ResolvedState yet.** Phase 6 (B4) adds it. For now, `ResolvedState` has `loaded` and `graph` only.

## Patterns to Follow

Look at how `sync::execute()` currently threads state through local variables. The phase struct approach replaces those locals with struct fields. The `execute()` function should become ~15 lines — just the chain of phase calls with the frozen gate check in between.

## Verification Criteria

- [ ] `cargo build` compiles cleanly
- [ ] `cargo test` — all existing tests pass (zero regressions)
- [ ] `cargo clippy` — no new warnings
- [ ] `execute()` function is <20 lines — just phase function calls
- [ ] Each phase function is independently callable (takes prior state, returns next state)
- [ ] No behavior change — `mars sync` produces identical output before and after

## Agent Staffing

- **Coder:** 1x gpt-5.3-codex
- **Reviewers:** 2x — correctness focus (verify no behavior change), design alignment (verify struct nesting matches design)
- **Tester:** 1x smoke-tester — run `mars sync` on a test project before and after, diff the outputs

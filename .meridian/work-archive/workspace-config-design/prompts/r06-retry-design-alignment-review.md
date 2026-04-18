# R06 Retry — Design-Alignment Review

Read `r06-retry-context-brief.md` first. That is the shared ground truth — do not re-derive it.

## Your Focus

You are the **design-alignment reviewer**. Question you must answer:

> Given the current R06 skeleton + the diagnosed `PreparedSpawnPlan` barrier, is the hexagonal design still coherent and shippable with a DTO reshape — or has this cycle exposed that hexagonal is the wrong pattern for this domain?

## What to Read

1. `.meridian/work/workspace-config-design/design/refactors.md` — R06 section specifically
2. `.meridian/work/workspace-config-design/design/architecture/overview.md`
3. `.meridian/work/workspace-config-design/design/architecture/` — any of the other architecture files that touch launch
4. `.meridian/work/workspace-config-design/decisions.md` — skim for R06-related decisions (grep R06, hexagonal, factory)
5. Current source:
   - `src/meridian/lib/launch/context.py`
   - `src/meridian/lib/launch/plan.py`
   - `src/meridian/lib/launch/process.py`
   - `src/meridian/lib/launch/runner.py`
   - `src/meridian/lib/ops/spawn/prepare.py`
   - `src/meridian/lib/app/server.py` (composition points near `:~319`)
   - `src/meridian/lib/harness/adapter.py` — `SpawnRequest`, `SpawnParams`, `PreparedSpawnPlan`, `ExecutionPolicy` shapes

## What to Produce

A markdown report at `$MERIDIAN_WORK_DIR/reviews/r06-retry-design-alignment.md` with:

### 1. Intent vs current state
- Does the skeleton realize the hexagonal intent, or does it *look* hexagonal while composition still lives in driving adapters? Cite specific file:line.
- Is the `LaunchContext` sum type the right abstraction, or is it papering over a structural problem?

### 2. The DTO barrier — confirm or refute
- Is `PreparedSpawnPlan` genuinely the structural blocker to Fix 1/2, or is the reviewer's diagnosis wrong?
- If confirmed: what minimum DTO reshape unblocks real centralization without cascading rework? Options to consider:
  - (i) Narrow `PreparedSpawnPlan` to `SpawnRequest` + unresolved profile/sandbox/approval
  - (ii) Keep `PreparedSpawnPlan` but split into `UnresolvedPreparedPlan` (pre-factory) and `ResolvedPreparedPlan` (post-factory)
  - (iii) Drop `PreparedSpawnPlan` entirely, factory takes a struct of raw inputs
  - (iv) Something else you see

### 3. Is hexagonal even right?
- Does this domain (harness launch: policy resolution + env building + command building + session-id observation + fork materialization) actually map cleanly to ports-and-adapters, or is the hexagonal frame being forced?
- Alternative shapes worth naming: pipeline/stages with typed stage inputs, command pattern, effect system (IO monad-style), plain function composition with typed glue, builder pattern, etc.

### 4. Verdict
Pick one:
- **proceed-with-dto-reshape** — hexagonal intent is right, a scoped DTO redesign unblocks. Recommend reshape (i), (ii), (iii), or (iv).
- **rethink-shape** — hexagonal is forced. Recommend alternative shape + rough sketch of it on this domain.
- **defer-decision** — insufficient evidence. What else do you need?

### 5. Risks
Top 3 risks regardless of which path is chosen.

## Style

Caveman full style — terse, fragment-friendly, technical terms exact. Code pointers carry their own weight; don't narrate them.

## Termination

Terminate with your report path and the verdict.

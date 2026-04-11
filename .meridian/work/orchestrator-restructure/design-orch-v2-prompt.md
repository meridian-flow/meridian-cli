# Revise orchestrator-restructure design draft

A first-draft design package lives at `$MERIDIAN_WORK_DIR/design/` describing a restructure of the dev-orchestrator topology. The user has revised the direction on three related points. Your job is to update the design package so it reflects the new direction coherently, then run your normal review fan-out to converge on a revised package.

Read the entire existing draft first — every file in `design/` plus `decisions.md`. Understand what is being kept and why before changing anything.

## Direction changes from the user

### 1. Do not delete @planner

The first draft deletes the @planner agent and folds self-planning into impl-orchestrator's own context. The user has reversed this call. @planner stays as an agent profile, but the caller changes — it was spawned by @dev-orchestrator, and now it is spawned by @impl-orchestrator.

Rationale the user gave: decomposition is real craft worth a dedicated agent with its own context window. Folding it into impl-orch conflates two different modes (decompose vs execute) in one context, which is exactly the kind of blurred-role problem the restructure was trying to fix on the other side. Giving @planner a narrower caller (impl-orch instead of dev-orch) puts the decomposition work closer to the runtime information it needs, without collapsing the role.

The self-planning "phase" is still the first thing @impl-orchestrator does — but it is a @planner spawn, not in-context work. @impl-orchestrator feeds @planner the design package plus terrain observations plus feasibility answers, waits for plan artifacts to materialize on disk, then reports back to @dev-orchestrator for the plan review checkpoint. Everything downstream of the plan review is unchanged.

### 2. Planner focus sharpens to parallelism-first decomposition

@planner's job is not "write a plan." It is "decompose the work so that as much as possible can run in parallel." The planner body should make this the central frame.

Concrete shape the user described:

- Structural refactors that touch many files land first. These are the cross-cutting changes that would create merge conflicts if they ran late. Getting them out of the way early unlocks downstream phases to run in parallel without stepping on each other.
- After structural prep lands, feature phases that operate on disjoint modules run in parallel.
- Phase ordering is justified by what it unlocks for parallelism, not just by logical dependency. Two phases can be logically independent but still have to be sequenced because they share a test harness or touch the same registry — the planner should surface those constraints explicitly.

The existing `planning` skill (in meridian-dev-workflow) needs to be revisited with this frame. You do not need to rewrite it in this design pass, but the design docs should name it as a follow-up and describe what the skill's emphasis should shift to.

### 3. Structure and modularity are first-class design concerns

The user's framing: "structure and modularity and SOLID are important so we can move fast with parallel work." This is not abstract craftsmanship — it is the enabler that makes parallelism-first planning possible at all. If the design lands a tangled structure, the planner cannot decompose it for parallelism no matter how hard it tries.

The lesson the user cited: a prior session produced a broken structure after design converged, and the wrongness only surfaced during implementation. That was a design-phase miss. Design-orchestrator should surface structural seams and modularity concerns more forcefully during its own convergence, not wait for implementation to discover them.

How this lands in the design docs:

- Design-orchestrator's body should carry explicit emphasis on modularity, cohesion, and interface boundaries as design-time concerns, not just implementation concerns. The feasibility questions already ask "does something need foundational work first?" — but that question can be answered "no" by a design that has missed the structural problem entirely. The answer has to be paired with active structural review.
- The Terrain section in `design/overview.md` should call out not just the current coupling, but whether the designed target state fixes it or preserves it. A design that lands "same tangled structure, new features bolted on" is a design that cannot be decomposed for parallelism.
- The reviewer fan-out should include a structural/refactor reviewer by default in the design phase, with explicit instructions to flag when the design is not modular enough to enable parallel work downstream.

## What to update

- **overview.md** — revise the topology description to keep @planner, describe the new caller relationship, update the "what gets deleted" and "what gets added" lists. Strengthen the framing on structure/modularity as design-time concerns.
- **design-orchestrator.md** — add the structural review emphasis. The Terrain section content is largely right but should incorporate the "does the target state fix the structural problem or preserve it" lens.
- **impl-orchestrator.md** — largest revision. The self-planning phase is now a @planner spawn, not in-context work. Skills loaded list shrinks (planning skill moves back off impl-orch). The review checkpoint after plan materialization still exists. The escape hatch is unchanged.
- **dev-orchestrator.md** — revise the delegation chain to show impl-orch is the one that spawns planner, not dev-orch. The autonomous redesign loop and loop guards are unchanged.
- **planner.md** (new doc in `design/`) — describe the revised @planner agent: its role under the new caller, its parallelism-first emphasis, what it consumes (design package + terrain + feasibility answers), what it produces (plan artifacts on disk), what skills it loads, and the framing shift in the `planning` skill that needs to happen downstream.
- **decisions.md** — revise D1 (do not delete planner, rehome caller instead) and add new decisions for the parallelism-first framing and the structural review emphasis. Keep the original alternatives and reasoning that still apply; record the reversal explicitly so future readers understand why the direction changed mid-draft.
- **feasibility-questions.md** — no change needed unless you judge the parallelism question should shift emphasis. If you revise it, keep it minimal.
- **redesign-brief.md** — no change needed.

## Convergence

Run your normal design-orchestrator loop: iterate with architects or do it in-context, fan out reviewers across diverse strong models with focus areas (design alignment, structure/modularity, decomposition sanity), and converge on a revised package. The review fan-out matters more than usual here because the reversal on @planner deletion is a real direction change and needs cross-model scrutiny.

Write the revised package back to `$MERIDIAN_WORK_DIR/design/` and update `$MERIDIAN_WORK_DIR/decisions.md` with the new decisions and the rationale for reversals. The existing draft is the starting point — preserve what is still correct, revise what is affected by the direction change.

Return a terminal report summarizing what changed between draft v1 and the revised package, and flagging any reviewer findings that the user should look at before approving.

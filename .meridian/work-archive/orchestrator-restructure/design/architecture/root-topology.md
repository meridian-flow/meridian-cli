# A00: Root topology

## Summary

Root-scope architectural invariants for the orchestrator system: the state-on-disk axiom, the three-orchestrator count (dev-orch, impl-orch, design-orch), the altitude asymmetry between spec (contract) and architecture (observation), and the current-vs-target posture that feeds the refactor agenda. Lives in a reserved-namespace leaf so that `refactors.md` entries can cross-link to root-scope structural concerns via the `Architecture anchor` field.

## Realizes

- `../spec/root-invariants.md` — S00.u1 (state on disk as authority), S00.u2 (one active agent per role), S00.s1 (crash-only lifecycle across hand-offs).
- `../spec/design-production/architecture-tree.md` — S02.2.s1 (root topology in reserved-namespace leaves), S02.2.s2 (observations, not recommendations).

## Current state

- **State root** — `.meridian/` (flat layout, JSONL event stores + per-spawn artifact dirs + shared filesystem). Path resolution lives in `src/meridian/lib/state/paths.py`.
- **Harness adapters** — `src/meridian/lib/harness/` (per-harness command building, output extraction, materialization). Adding a harness is one adapter file + registration.
- **State layer** — `src/meridian/lib/state/` (spawn store, session store, work store). Atomic writes via tmp+rename, `fcntl.flock` for concurrency.
- **Spawn lifecycle** — `meridian spawn` creates spawn records, harness adapter launches the underlying process, heartbeat file tracked for liveness, terminal report emitted on completion. Crash-only: reads tolerate truncation, reconciliation lives on read paths via `meridian doctor`.
- **Orchestrator altitudes today** — dev-orchestrator (user-facing, requirements.md + design walk), impl-orchestrator (execution-only in v2, pre-planning + planning + execution in v3), design-orchestrator (design package authoring), @planner (decomposition, spawned by dev-orch in v2).

## Target state

### A00.1 — Three orchestrators, strict role separation

- **dev-orchestrator** (one per work item, interactive with user) — owns requirements capture, design approval walk, plan review checkpoint, autonomous redesign loop, preservation hint production, K=2 redesign cycle counter.
- **impl-orchestrator** (two spawns per work item on first-cycle work — one planning, one execution; plus one additional planning spawn per redesign cycle) — owns pre-planning runtime probes, @planner spawn, pre-execution structural gate, plan-ready terminal report, per-phase execution loop, spec-drift enforcement via escape hatch, K_fail=3 + K_probe=2 planning cycle cap.
- **design-orchestrator** (one spawn per design cycle, including initial + every redesign cycle) — owns spec tree authoring (directly from requirements.md, spec-first), architecture tree authoring (derived from spec), refactors.md authoring, feasibility.md authoring, dev-principles as shared convergence lens, structural reviewer requirement.

### A00.2 — State on disk as the only authority

All orchestrator state lives in files under `.meridian/` and `$MERIDIAN_WORK_DIR/`. No in-memory state crosses spawn boundaries. This is the crash-only axiom — every orchestrator is a stateless process that reads its inputs from disk on startup, does its work, writes its outputs to disk, and terminates. A resumed spawn is indistinguishable from a fresh spawn that read the same disk state.

### A00.3 — Spec tree is contract, architecture tree is observation

Spec leaves are authoritative: impl-orch may not deviate from a spec leaf without routing through the escape hatch or a scoped design revision cycle. Architecture leaves are observational: impl-orch may deviate from the architecture tree's observational shape when runtime evidence supports it, provided the deviation is logged in decisions.md per S02.2.s2. The asymmetry is load-bearing — treating architecture leaves as contract would collapse the runtime-correction flexibility the execution loop depends on; treating spec leaves as observation would collapse the verification contract that keeps code aligned to user intent.

### A00.4 — Current vs target posture for the orchestrator code

| Area | Current (v2) | Target (v3) |
|---|---|---|
| Design package shape | Single `design/` flat directory with `overview.md` carrying Terrain section prose | Two-tree hierarchical `design/spec/` + `design/architecture/` + sibling `design/refactors.md` + `design/feasibility.md` |
| Verification contract | `scenarios/` folder with S001-style scenario files, `plan/scenario-ownership.md` | Spec leaves with EARS statements, `plan/leaf-ownership.md` at EARS-statement granularity; `scenarios/` convention retired |
| Refactor agenda | Terrain section inside `overview.md`, `structural-prep-candidate: yes|no` tags | First-class `design/refactors.md` artifact with nine-field per-entry shape, nine-field read by @planner directly |
| Feasibility record | Impl-orch runs probes during pre-planning; design-time probes not recorded | First-class `design/feasibility.md` artifact with Probe records / Fix-or-preserve / Assumption validations / Open questions sections |
| dev-principles role | Proposed binary convergence gate | Shared behavioral lens loaded by every agent, principle violations routed through normal reviewer-finding loop (D24 revised) |
| Planner caller | Dev-orch spawns @planner before impl-orch runs | Planning impl-orch spawns @planner after pre-planning runs, terminated-spawn contract to dev-orch for plan review |
| Redesign loop | Manual escalation to user on bail-out | Autonomous dev-orch routing of design-problem vs scope-problem with K=2 redesign cycle counter |

## Interfaces

- **`meridian spawn ...`** — spawns a subagent; state persisted under `.meridian/spawns/<spawn_id>/`. Used by every orchestrator to delegate work.
- **`meridian work ...`** — work-item lifecycle, dashboard, session listing. Used by dev-orch for work-item creation; used by all orchestrators for status tracking.
- **`meridian spawn report create --stdin`** — emits a terminal report that parents read via `spawn show` or `spawn wait`. Used by every agent on completion.
- **`$MERIDIAN_WORK_DIR`** — per-work-item scratch directory. Layout defined in A02.2. All agents read and write here.
- **`$MERIDIAN_FS_DIR`** — shared long-lived filesystem (domain docs, reference material). Read by all agents; written by @code-documenter via @docs-orchestrator coordination.

## Dependencies

- **`src/meridian/lib/state/`** — every orchestrator's on-disk state lives here.
- **`src/meridian/lib/harness/`** — spawn launches go through the harness adapter for the chosen harness. Policy (which model, which approval mode) lives in agent profiles and `meridian config`; mechanism (how to launch) lives in adapters.
- **`.agents/`** — agent profiles and skill files, materialized from `mars.toml` via `meridian mars sync`. Never hand-edited per CLAUDE.md.

## Open questions

None at the architecture-tree level. Root-scope unresolved items are tracked as decisions in `../decisions.md` per the spec-first ordering rule (S02.1.e1).

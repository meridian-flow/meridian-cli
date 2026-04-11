# v2 design package reviewer synthesis

Four reviewers ran in parallel (p1528 r1 alignment gpt-5.4, p1529 r2 structure gpt-5.2, p1530 r3 parallelism opus, p1531 r4 refactor gpt-5.4). All four returned `request changes`. Findings consolidated below by theme; convergent themes flagged with reviewer count.

## Convergent themes (multi-reviewer)

### T1 — Parallelism-first frame is rhetoric, not infrastructure (r3 H1, r3 M3, r3 L1)
One reviewer but the most damning structural critique. The central frame lives in one sentence in `planner.md` and one decision entry. Nothing downstream — `/planning` skill body, planner profile body, blueprint format, plan-overview format, dev-orch review criteria, re-spawn triggers — is changed. A planner spawned under v2 will produce v0-shaped plans.

Fix:
- Inline the parallelism-first frame into the planner profile body (NOT just leave as follow-up). Mandate `/planning` skill update as a hard gate before any v2 plan ships.
- Add concrete `Parallelism Posture` field + `parallelism justification` template to plan/overview.md format (define in planner.md outputs).
- Add explicit parallelism review criteria to dev-orch plan review checkpoint.
- Add re-spawn trigger: "plan is sequential when disjoint modules exist OR parallelism justifications hand-wavy/missing."

### T2 — Structurally non-decomposable design has no corrective path (r1 MEDIUM, r2 CRITICAL, r3 M5)
Three reviewers converge. Planner is told to flag "cannot decompose for parallelism" back to impl-orch but no doc describes what impl-orch does with that signal. Escape hatch is execution-only; no planning-time bail-out.

Fix:
- Add `Parallelism Posture` field (parallel|limited|sequential) + cause classification (inherent constraint vs structural coupling preserved by design) to plan/overview.md.
- impl-orch: if posture=sequential due to structural coupling, stop before execution and emit redesign brief OR escalate to dev-orch with structural-blocking signal.
- dev-orch: treat structural-coupling-sequential as blocking unless user explicitly accepts the tradeoff.
- Extend escape hatch (D5) to include planning-time falsification.
- Add 7th optional section to redesign-brief: "Parallelism-blocking structural issues discovered post-design."

### T3 — Stale v1 wording in feasibility-questions.md (r1 LOW, r4 HIGH)
Both reviewers flag intro "two loaders" and `self-planning phase` reference. Easy fix.

### T4 — Terrain contract is shared but lives inside design-orchestrator.md (r3 H3, r4 HIGH)
Two reviewers, different angles, same root: Terrain is consumed by design-orch (producer), impl-orch (pre-planning context), and planner (decomposition input), but the contract lives in design-orchestrator.md. r4 says extract to standalone artifact spec. r3 says require explicit tagging of structural delta items as "structural prep candidates" so the planner has a structured handoff.

Fix:
- Extract Terrain contract to standalone `design/terrain-contract.md` with required template + evidence requirements.
- design-orch produces structural delta with explicit `structural-prep-candidate: yes|no` tags on each item.
- planner.md: explicit input requirement to map each candidate to phase or skip with reason.

## High-severity single-reviewer findings

### H-r1-1 — Plan-review pause/resume contract internally inconsistent (r1 HIGH)
dev-orchestrator.md says "same spawn or fresh one"; impl-orchestrator.md says impl-orch reports plan and waits.

Fix: pick one model. Recommend **terminated spawn returning report → fresh impl-orch spawn for execution if approved**. This avoids holding state in suspended processes (matches crash-only design philosophy of meridian).

### H-r1-2 — Preservation hint not defined as a data contract (r1 HIGH)
dev-orch introduces "preservation hint" for restart-after-redesign; no doc defines artifact format, how impl-orch consumes it, or how plan/status.md represents preserved/partial/replanned phases.

Fix: define `plan/preservation-hint.md` format (preserved phases, invalidated phases, replan-from-here marker). Specify impl-orch consumption rule. Specify plan/status.md status values (`preserved`, `replanned`, `not-started`).

### H-r2-1 — Structural reviewer mandate language is contradictory (r2 HIGH)
"by default" + "mandatory" + "not a separate mandatory pass" creates a loophole.

Fix: normalize to "required reviewer inside the standard fan-out (no separate phase), never skipped." Add convergence rule: design-orch may not declare convergence without structural reviewer PASS or documented override.

### H-r2-2 — Terrain "fix or preserve" needs evidence (r2 HIGH)
Vibes-based "fixes coupling" can still pass.

Fix: add `fix_or_preserve: fixes|preserves|unknown` enum (`unknown` blocks convergence). Require named module-level cuts. Require at least one parallel-cluster-after-prep hypothesis.

### H-r3-2 — Planner re-spawn loop unbounded (r3 H2)
No cycle cap on planner re-spawns. Pathological ping-pong possible.

Fix: K=3 planning-cycle cap. After exhaustion, impl-orch emits "planning-blocked" escalation to dev-orch (distinct from execution-time falsification). Add D12 documenting the cap.

### H-r3-4 — Pre-planning chicken-and-egg unresolved (r3 H4)
impl-orch must enumerate constraints before knowing what decomposition they serve.

Fix: pick path (a with scoping) — impl-orch enumerates module-scoped constraints WITHOUT a tentative decomposition. Constraints are stated as "modules X and Y share fixture Z; whoever decomposes must respect that." Planner maps constraints to phases. Document in impl-orchestrator.md and D3.

## Medium-severity findings

- **r3 M1** — overclaim of runtime-context equivalence: notes file is a filtered projection; acknowledge asymmetry; add probe-request channel via planner's "missing data" output.
- **r3 M2** — anthropomorphic "cognitive modes" framing: rewrite with LLM-specific arguments (fresh context isolation from execution state, materialized compaction-tolerant artifacts, separate skill/model loadout).
- **r3 M4** — terminology collision "structural refactors" (planner.md) vs "foundational work" (feasibility-questions.md). Reconcile: structural refactors = rearrangement; foundational scaffolding = new dependency creation; cross-reference both.
- **r3 M3** — dev-orch plan review has no criteria. Covered by T1 fix.
- **r4 MED-1** — component docs mix steady-state contract with migration notes. Recommend leaving "what is deleted / added" sections in place (they're needed for the v1→v2 reversal) but ensure they don't bleed into the steady-state body.
- **r4 MED-2** — decisions.md needs top summary + thematic grouping. Add executive summary at top.
- **r4 MED-3** — duplicated planner rationale across overview/component docs. Centralize in decisions.md, keep component docs concise.

## Low-severity findings

- **r2 LOW** — SOLID not operationalized. Add SOLID-as-signals mapping (SRP/ISP/DIP) to structural reviewer brief.
- **r3 L1** — parallelism justification template missing. Covered by T1 fix.
- **r3 L2** — redesign-brief format lacks parallelism-failure section. Covered by T2 fix.
- **r3 L3** — planner cannot request probes. Document the probe-request channel via re-spawn output.

## Open question

- **r1 open** — design-orchestrator.md line 57 "not a separate mandatory pass" vs lines 91 + decisions.md line 125 hard requirement. Tighten language. Covered by H-r2-1 fix.

## Application order

1. New artifact: `design/terrain-contract.md` (extracts Terrain spec, adds template + evidence requirements + structural-prep tagging) — fixes T4, H-r2-1, H-r2-2
2. `design/planner.md` updates — fixes T1, T2, T3 (probe channel), H-r3-2 cycle cap, M2 reframe, M4 reconcile
3. `design/impl-orchestrator.md` updates — fixes T2 structural gate, T5 pause/resume, T7 cycle cap, H4 chicken-and-egg, M5 escape hatch extension
4. `design/dev-orchestrator.md` updates — fixes T5 pause/resume, T6 preservation hint, T1 review criteria, T2 structural-blocking
5. `design/design-orchestrator.md` updates — fixes T4 reference Terrain contract, H-r2-1 mandatory language, structural reviewer brief
6. `design/feasibility-questions.md` cleanup — fixes T3, M4 reconcile
7. New artifact: `design/preservation-hint.md` (or section in dev-orchestrator.md/redesign-brief.md) — fixes T6
8. `design/redesign-brief.md` updates — adds 7th section for parallelism-blocking structural issues
9. `decisions.md` updates — D5 extension, D7 update, new D12 (planning cycle cap), D13 (Terrain contract extraction), top summary

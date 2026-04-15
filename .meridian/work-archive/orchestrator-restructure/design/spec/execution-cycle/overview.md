# S05: Execution Cycle — Subsystem Overview

## Purpose

This subsystem covers the execution impl-orchestrator's cycle from approved plan to phase-complete commits, with spec-leaves as the verification contract and the escape hatch as the bail-out channel for spec-leaf falsification. The execution impl-orch is a fresh spawn separate from the planning impl-orch — it consumes the approved plan attached via `-f` and starts directly at the execution loop without re-running pre-planning or the @planner spawn. Verification is keyed to EARS statements in spec leaves, not to a separate scenarios convention. This overview is a strict TOC; substantive EARS requirements live in the leaf files.

## TOC

- **S05.1** — Per-phase execution loop ([phase-loop.md](phase-loop.md)): read phase blueprint, spawn coder, spawn testers on claimed spec leaves, iterate fix loop until all claimed leaves verify, commit, move to next phase; plus the parallel-round execution for phases the planner marked parallel-eligible.
- **S05.2** — Spec-leaf verification ([spec-leaf-verification.md](spec-leaf-verification.md)): testers parse the EARS statement into trigger/precondition/response per the mechanical parsing rule, execute smoke tests against the triple, and report verified/falsified/not-covered per leaf at EARS-statement granularity.
- **S05.3** — Spec-drift enforcement ([spec-drift.md](spec-drift.md)): runtime evidence contradicting a spec leaf fires the escape hatch before any code workaround lands; the spec is revised first, code follows.
- **S05.4** — Escape hatch (execution-time and planning-time) ([escape-hatch.md](escape-hatch.md)): both arms keyed on spec-leaf falsification, redesign brief format and justification burden, what does and does not warrant bail-out.
- **S05.5** — Preserved-phase re-verification ([preserved-reverification.md](preserved-reverification.md)): tester-only re-verification for preserved phases whose spec leaves were revised in-place, with three outcomes (all verify / some falsify / cannot execute) and the promote-to-partially-invalidated path.

## Reading order

Read S05.1 first — the per-phase loop is the default control flow. Then S05.2 for the verification contract that shapes what testers execute, then S05.3 for the spec-drift discipline that keeps code aligned to spec, then S05.4 for the escape hatch that bails out when spec is falsified, then S05.5 for the redesign-cycle-specific re-verification pass. The corresponding architecture content lives in `../../architecture/orchestrator-topology/execution-loop.md` (A04.2) and `../../architecture/verification/` (A03).

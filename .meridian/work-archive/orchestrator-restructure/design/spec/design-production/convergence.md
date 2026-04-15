# S02.4: Design convergence

## Context

Convergence is the point at which design-orch declares the design package (spec tree + architecture tree + refactors.md + feasibility.md) ready for dev-orch's approval walk. Under v3, convergence is a multi-lens judgment — functional coverage, spec-testability, structural decomposability, principle adherence — not a single binary pass. A design that is functionally correct and internally consistent can still be structurally non-decomposable; v3 catches that at design time via the required structural reviewer rather than letting it leak into execution (D11). `dev-principles` participates as a shared lens during convergence, not as a pass/fail gate (D24 revised).

**Realized by:** `../../architecture/orchestrator-topology/design-phase.md` (A04.4) and `../../architecture/principles/dev-principles-application.md` (A05.1).

## EARS requirements

### S02.4.u1 — Convergence is multi-lens

`The design-orch convergence flow shall judge the design against four lenses simultaneously: functional coverage, spec testability, structural decomposability, and principle adherence.`

### S02.4.e1 — Reviewer fan-out includes spec, architecture, alignment, structural, feasibility lanes

`When design-orch runs the convergence reviewer fan-out, the fan-out shall include at least one spec reviewer (EARS enforcement focus), one architecture reviewer (structural soundness focus), one alignment reviewer (cross-link integrity focus), one required structural/refactor reviewer (decomposability focus), and optionally a feasibility reviewer, spawned across diverse strong model families with non-overlapping blind spots.`

### S02.4.e2 — Structural reviewer is required and blocks PASS

`When design-orch declares convergence, the structural reviewer shall have returned a PASS verdict or an explicit override shall be recorded in decisions.md with rationale, and the declaration shall not stand in the absence of both.`

### S02.4.s1 — Convergence exit requires addressed findings, not clean first pass

`While design-orch is running a reviewer loop, convergence shall be declared only after every reviewer finding (including principle violations surfaced via dev-principles) has been either resolved in the design or explicitly overridden in decisions.md with rationale — a first-pass clean review is not required, but a final state with unresolved findings blocks convergence.`

### S02.4.s2 — Spec reviewer enforces EARS shape

`While the spec reviewer is auditing design/spec/, any leaf containing an acceptance criterion that is not one of the five EARS patterns, that hides multiple behavior commitments inside one statement, or that fails the mechanical parse check (per D25 and ../../architecture/verification/ears-parsing.md), shall be flagged as REQUEST CHANGES and block convergence.`

### S02.4.s3 — Non-requirement flags must be audited

`While the spec reviewer is auditing design/spec/, every edge case flagged as "non-requirement with reasoning" instead of as an EARS statement shall be checked for explicit, falsifiable reasoning — a bare "out of scope" without architectural justification shall be flagged as REQUEST CHANGES.`

### S02.4.s4 — Structural reviewer sketches decomposition before PASS

`While the structural reviewer is auditing design/architecture/ + design/refactors.md, the reviewer shall identify at least one candidate cross-cutting prep cut from refactors.md that the planner would land first, identify at least two candidate parallel clusters from the architecture tree that could run after the prep lands, and block PASS if the sketch fails (no prep cuts visible, fewer than two clusters identifiable).`

### S02.4.w1 — `dev-principles` as shared behavioral lens

`Where design-orch runs convergence, design-orch shall load the dev-principles skill and walk each principle against the current design (refactor discipline, edge-case thinking, abstraction judgment, deletion courage, existing patterns, structural health signals, integration boundary probing, doc currency), treating violations as reviewer findings routed through the normal loop rather than as a separate binary gate.`

**Edge cases.**

- **No separate gate.** There is no PASS/FAIL checkpoint on `dev-principles` specifically. The skill is a lens, not a mechanism (D24 revised). Findings fold into the reviewer loop alongside every other finding.
- **Principle tradeoffs recorded.** When design-orch intentionally keeps a tradeoff that violates a principle (e.g. a preparatory refactor is deferred for a stated reason), the tradeoff and its reasoning land in decisions.md. The record is how downstream agents and auditors understand why a principle was not fully applied.

### S02.4.c1 — Spec-first ordering is a convergence criterion

`While design-orch is running convergence, when the spec reviewer or alignment reviewer surfaces evidence that architecture leaves shaped spec leaves (rather than the reverse), the reviewer shall flag the finding as a spec-first violation and block PASS until the affected spec leaves are rewritten from user intent.`

## Non-requirement edge cases

- **Minimum reviewer count.** v3 does not fix a hard minimum number of reviewers. Small-path work items may get two reviewers; large-path work items may get six or more. The rule is "cover every lens with at least one reviewer, duplicate coverage on high-risk axes." Flagged non-requirement because a hardcoded count would waste reviewer budget on trivial work.
- **Automated convergence detection.** A future tool could scan reviewer reports and declare convergence automatically. Rejected as a non-requirement because the convergence judgment is partly about whether findings were addressed well, which reviewer-report scanning cannot evaluate. Design-orch's judgment is load-bearing here.

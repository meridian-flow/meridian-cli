# Produce `design/feasibility.md` for orchestrator-restructure v3

`design/feasibility.md` is a first-class artifact defined by D20 in `$MERIDIAN_WORK_DIR/decisions.md` — the record of what design-orch actively probed during the design phase, what evidence the probes produced, and what design constraint each piece of evidence grounds. Downstream planners, reviewers, and impl-orch's pre-planning step read it as the authoritative evidence base for v3 design choices.

Produce the file at `$MERIDIAN_WORK_DIR/design/feasibility.md`. If the file already exists (unlikely — it's new in v3), preserve existing content and append.

## Source material

Read before writing:
- `$MERIDIAN_WORK_DIR/decisions.md` — D20 for the artifact's purpose, D11 for structural-review context, D16–D26 for the decisions that need grounding.
- `$MERIDIAN_WORK_DIR/reviews/` — v2 reviewer reports (spawn IDs p1536, p1537, p1538, p1547 per the p1535 convergence report). These are the concrete findings that drove v2→v3 revisions.
- `$MERIDIAN_WORK_DIR/design/terrain-contract.md` — §"Fix-or-preserve verdict" defines the shape of that section and lives inside feasibility.md per the contract.
- `$MERIDIAN_WORK_DIR/design/overview.md` — "Where v3 sits on Fowler's SDD spectrum" subsection (added by p1535) for the research grounding.
- The other existing flat design docs under `$MERIDIAN_WORK_DIR/design/` — enough to understand the target system being grounded.

## Content shape

Each entry answers three questions: **what was checked**, **what the evidence showed**, **what design constraint it produced** (with an explicit pointer to the decision or doc that carries the constraint).

Concrete sections to include:

1. **Probe records.** What was run or examined, what output was observed, what constraint emerged. For orchestrator-restructure the probes include:
   - v2 reviewer fan-out (four reviewer spawns with finding clusters) — cite spawn IDs and finding IDs where possible. Each finding that drove a v2→v3 revision is a probe record.
   - SDD research probe — Fowler's three levels, Kiro's EARS convention, Thoughtworks business/technical separation, Addy Osmani's hierarchical TOC pattern. Each source with what it showed and what design constraint it grounded. The research anchors list in the v3 design-orch prompt is a starting index.
   - Prior-session broken-structure lesson — a real observed failure where a prior design session converged with a structurally tangled design and the problem surfaced only during implementation. This grounds D11 (structural review mandate) and the "structure as design-phase concern" principle in v3.
   - Env-propagation-fix incident (GitHub issue #12) — meridian's own env layer had a regression that broke meta-design workflows because MERIDIAN_WORK_DIR stopped inheriting correctly. Relevant as meta-evidence: inheritance assumptions drift and the spec-drift enforcement rule in D6/D26 is the counter.

2. **Fix-or-preserve verdict.** For each structural concern in the current topology, state whether v3 fixes it or preserves it, with evidence. The concerns to cover:
   - v2's `scenarios/` convention drift (D22 retires it — evidence: the v2 authors forgot to maintain the convention, so the verification contract evaporated)
   - v2's flat design doc set (D18 tree restructures it — evidence: 9 docs × ~30KB each = ~280KB of prose with no navigation index)
   - v2's Terrain section as a single overloaded concept (D18+D19+D20 split it into three named artifacts — evidence: reviewers couldn't distinguish architecture, refactors, and feasibility material within one section)
   - v2's "gate" framing for `dev-principles` at impl-orch (user correction: universal skill loading — evidence: gating implies binary pass/fail, which doesn't fit behavioral principles)
   - v2's scenario-ownership tracking (D22 migrates to leaf-ownership — evidence: scenarios subsumed by spec leaves, ownership follows)

3. **Assumption validations.** Places where v3 rests on assumptions about downstream systems (harness behavior, meridian spawn model, env propagation, etc.) that we probed or should probe.

4. **Open questions.** Feasibility questions that remain unresolved. Flag them so planner or impl-orch knows to probe at their respective altitudes.

## Quality bar

Every entry earns its length by grounding a design choice or constraint downstream. Vibes-based evidence ("this feels coupled," "seems problematic") falls outside the scope of this artifact — `terrain-contract.md` §"Evidence field" explicitly rejects it, and feasibility.md follows the same rule.

Keep entries tight. Speculative claims without a concrete probe or cite don't earn a place. If you can't link an entry to a specific piece of evidence (spawn ID, research URL, log excerpt, commit SHA, decision ID), the entry isn't grounded — drop it or mark it as an open question.

## Format

Markdown. Organize by the sections above. Each entry uses three-field structure: **Checked**, **Observed**, **Constraint**. Cross-link to decisions and other design docs using relative markdown links.

## Return

Terminal report naming:
- The sections written
- Total line count
- Any evidence you could not find (gaps that suggest a re-probe)
- Any places where a probe revealed a gap deserving its own decision entry (flag for design-orch to consider)

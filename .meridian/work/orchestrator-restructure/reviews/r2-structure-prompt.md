# Review request: orchestrator-restructure design v2 — structural emphasis sanity

You are reviewing the **second draft** of a design package that restructures the dev-workflow orchestration topology. Your specific focus is the **structure and modularity emphasis** that v2 added to design-orchestrator's body, and whether the new framing is strong enough to actually catch the failure mode it is meant to prevent.

## Why this review exists

A prior session in this repo produced a design that converged with reviewers and shipped — but the design landed a structurally tangled target state. The wrongness only surfaced during implementation, after the team was already committed. That was a design-phase miss masquerading as an implementation problem.

The user's framing: "structure and modularity and SOLID are important so we can move fast with parallel work." Structure is the enabler that makes parallelism-first planning possible at all. If the design lands a tangled structure, the planner cannot decompose it for parallelism no matter how hard it tries.

The v2 design package responds to this by:

1. Promoting structure/modularity to first-class **design-time** concerns, not implementation craft.
2. Adding "does the target state fix or preserve the existing structural problems?" as an explicit Terrain section question.
3. Mandating a structural/refactor reviewer in the design-phase reviewer fan-out.
4. Expanding convergence criteria from functional-only to functional + structural.

Your job is to evaluate whether these moves are actually strong enough to catch the failure mode, or whether they would let the same failure slip through again.

## What to read

Read everything in `$MERIDIAN_WORK_DIR/design/` and `$MERIDIAN_WORK_DIR/decisions.md`, paying particular attention to:

- `design/overview.md` — especially the "Why structure and modularity are first-class design concerns" section near the end
- `design/design-orchestrator.md` — especially the Terrain section content, the "Active structural review during convergence" section, and the reviewer fan-out section
- `design/planner.md` — especially "Why parallelism matters here specifically" — this is where the structural emphasis ties to the planner's downstream work
- `decisions.md` — especially D11 (structural review at design phase) and D10 (parallelism-first decomposition)

## What to check

1. **Is the structural review actually mandatory or just rhetorically encouraged?** A design that says "the structural reviewer is in the default fan-out" can still skip it on small designs if no one enforces the default. Is the mandate concrete enough that an actual design-orch instance would always include a structural reviewer? If not, propose stronger language.

2. **Is "fix or preserve" a question that can actually be answered?** It is easy to write a Terrain section that says "the design fixes the coupling" without backing it up. What instructions or evidence does the design-orch body give the writer to make sure the answer is real? Are the "structural delta" examples concrete enough?

3. **Will the structural reviewer have what it needs?** A reviewer told to "flag when the design is not modular enough" can produce vague findings without traction. What specific signals or anti-patterns should the reviewer be looking for? Is the brief in design-orchestrator.md for the structural reviewer specific enough that the reviewer can produce actionable findings?

4. **Does convergence actually require the structural axis to clear?** "Convergence requires functional + structural" is the stated bar. But review fan-out in this codebase iterates until reviewers stop finding issues. Is there a mechanism that prevents design-orch from declaring convergence when the structural reviewer has stopped finding new issues but the underlying structure is still tangled? Or is this just trusting the reviewer to be thorough?

5. **Does the parallelism-first frame in `planner.md` actually depend on the structural emphasis being correct?** The two are positioned as interlocking — D11 enables D10. But if the structural emphasis fails, does the planner have any fallback, or does it just produce a sequential plan and report? Trace the dependency from a structurally-failed design through the planner to the impl-orch execution loop. Where does the failure surface, and is it early enough?

6. **SOLID-style decomposability.** The user named SOLID explicitly. The design package uses words like "modularity, cohesion, interface boundaries" but does not lean hard on SOLID specifically. Should it? Or are the broader words sufficient? Take a position.

7. **Anti-pattern: rhetorical strength without operational teeth.** The riskiest failure mode for this kind of restructure is that the framing reads strong but produces no actual change in behavior because the operational mechanisms are weak. Look for places where the design says "this is important" without saying "and here is what changes when it isn't." Flag every such gap.

## How to report

Severity-tagged findings (CRITICAL / HIGH / MEDIUM / LOW). For each finding:

- **Where**: file and section
- **What**: the specific issue
- **Why it matters**: the consequence if shipped as-is
- **Suggested fix**: concrete change

Be adversarial. This part of the v2 draft is the response to a real prior failure, and the user explicitly wants it to be strong enough that the failure cannot recur. A "looks good" review would not catch the kind of weakness that produced the original failure.

Return your findings as a single report. No file edits — read-only review.

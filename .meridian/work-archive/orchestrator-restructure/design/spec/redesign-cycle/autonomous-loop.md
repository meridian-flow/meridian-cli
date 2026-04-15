# S06.1: Autonomous redesign loop and routing

## Context

The redesign loop is entered when an impl-orch terminal report cites a redesign brief. There are three entry signals, all routed through the same loop: execution-time falsification (execution impl-orch hit runtime evidence contradicting a spec leaf), structural-blocking (planning impl-orch's pre-execution structural gate fired), and planning-blocked (planning impl-orch's planner cycle cap exhausted or a structural-blocking short-circuit bypassed both counters). Dev-orch reads the brief directly, makes a design-vs-scope judgment, and routes accordingly. The loop runs without user input by default because the user is a bottleneck on response time, not on judgment — autonomy with visibility, not autonomy with opacity.

**Realized by:** `../../architecture/orchestrator-topology/redesign-loop.md` (A04.3).

## EARS requirements

### S06.1.u1 — Three entry signals, one loop

`The dev-orch redesign loop shall be entered by exactly three terminal-report signals: execution-time falsification, structural-blocking, and planning-blocked, and all three signals shall route through the same loop flow.`

### S06.1.e1 — Dev-orch classifies brief as design problem or scope problem

`When dev-orch reads a redesign brief, dev-orch shall classify the brief as either a design problem (needs design-orch re-engagement) or a scope problem (next impl-orch cycle can resolve with a narrower plan or additional probes), and the classification shall be based on the brief's evidence and the original requirements, not on user input.`

**Reasoning.** A brief that claims architectural falsification but cites only a single test failure is probably scope, not design. A brief that cites end-to-end smoke evidence against a protocol assumption is probably design. A structural-blocking brief is almost always a design problem — the planner is signaling that the design's target state preserves a coupling no decomposition can route around. A planning-blocked brief requires reading the gap reasoning to decide whether the design is unclear (design problem) or the pre-planning notes were incomplete (scope problem). The call lives in dev-orch because dev-orch is the one that has to answer to the user for the decision.

### S06.1.e2 — Design-problem routing spawns design-orch with scoped inputs

`When dev-orch classifies a brief as a design problem, dev-orch shall spawn design-orch with the original design package, the redesign brief as context, and a scoped instruction naming which parts of the design need revision, which parts should stay, and what the preservation list means for the revision, and shall wait for design-orch convergence as it would for any design session.`

### S06.1.e3 — Scope-problem routing spawns a fresh impl-orch

`When dev-orch classifies a brief as a scope problem, dev-orch shall either push back on the brief and ask impl-orch for a narrower justification, or spawn a fresh impl-orch with scope adjustments and no design-orch cycle, and shall not spawn design-orch or produce a preservation hint in this path because no design changed.`

### S06.1.s1 — Autonomy is the default; user is not a required approval step

`While dev-orch is handling a redesign brief, dev-orch shall route the cycle without waking the user for approval, because dev-orch has the original requirements, the full design context, and the brief — routing does not require human-unique information — and shall notify the user rather than block on the user.`

### S06.1.s2 — Autonomy with visibility, not autonomy with opacity

`While dev-orch is running the autonomous redesign loop, every bail-out shall trigger a user notification, every cycle shall be logged to decisions.md with its classification and routing decision, and the user shall remain able to intervene at any time via notification response, meridian work show, or pausing the orchestrator chain.`

### S06.1.c2 — Dev-orch pushes back on weak briefs

`While dev-orch is reading a redesign brief, when the brief fails the justification burden per S05.4.s1 (cannot name specific falsified leaves or cannot show the structure-resistance case), dev-orch shall reject the brief and push back on impl-orch to either patch forward or produce a stronger case, and shall not route the cycle on a weak brief.`

### S06.1.w1 — Design-problem routing triggers preservation hint production

`Where dev-orch routes a cycle as a design problem and design-orch returns with a revised design package, dev-orch shall produce the preservation hint per S06.2 before spawning the next planning impl-orch, and shall attach the hint to the planning impl-orch spawn via -f.`

### S06.1.s4 — Scope-problem paths skip hint production

`While dev-orch is routing a scope-problem path, dev-orch shall not produce a preservation hint and shall not spawn design-orch, because no design changed and there is nothing to preserve differently.`

## Non-requirement edge cases

- **User-approved redesign routing.** An alternative would require user approval before every redesign cycle. Rejected because the user is a bottleneck on response time, not on judgment — waking the user to say "this needs a redesign, should I redesign it?" is asking permission to do the thing that is already the right move. Flagged non-requirement because the autonomy rule is load-bearing for loop throughput.
- **Auto-routing to design-orch without dev-orch classification.** An alternative would route every brief directly to design-orch without dev-orch's classification step. Rejected because not every brief is a design problem — a planning-blocked brief where the gap is in pre-planning probe coverage is a scope problem that design-orch cannot resolve. Flagged non-requirement because the classification step is load-bearing for routing accuracy.
- **Dev-orch edits the brief before forwarding.** An alternative would let dev-orch revise the brief before routing to design-orch. Rejected because the brief is impl-orch's artifact and cross-author edits break the escalation audit chain. Flagged non-requirement because the single-author rule on briefs is load-bearing for routing trust.

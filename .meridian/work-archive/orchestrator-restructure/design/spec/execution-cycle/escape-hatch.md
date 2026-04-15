# S05.4: Escape hatch (execution-time and planning-time)

## Context

The escape hatch fires when runtime evidence falsifies a spec leaf the design rests on. There are two arms — execution-time and planning-time — and they share the same brief format (`redesign-brief.md`) but different sections. The execution-time arm fires when the execution impl-orch's fix loop hits runtime evidence contradicting a claimed spec leaf; impl-orch writes the brief, emits a terminal report, and routes to dev-orch. The planning-time arm has three triggers covered elsewhere — pre-planning contradiction of a leaf, planner cycle-cap exhaustion, and structural-blocking — all of which are also treated as escape-hatch emissions. The justification burden on every brief is the same: it must articulate why the evidence is falsification rather than fixable friction, and dev-orch will reject a weak brief and push back. The hatch is cheap to invoke but expensive to defend, which is the counterweight that prevents it from becoming a shortcut past hard work.

**Realized by:** `../../architecture/orchestrator-topology/execution-loop.md` (A04.2) and `../../architecture/orchestrator-topology/planning-and-review-loop.md` (A04.1).

## EARS requirements

### S05.4.u1 — Escape hatch has two arms

`The escape hatch shall have exactly two arms: execution-time falsification (fired by the execution impl-orch during the fix loop) and planning-time falsification (fired by the planning impl-orch at pre-planning contradiction, cycle-cap exhaustion, or structural-blocking), both using redesign-brief.md as the artifact shape.`

### S05.4.u2 — Brief is the load-bearing audit record

`Every escape-hatch emission shall produce a redesign brief at $MERIDIAN_WORK_DIR/redesign-brief.md that cites the specific falsified spec-leaf IDs (or, on planning-time emissions, the structural coupling the planner could not decompose around) and the runtime evidence that contradicts the leaf or coupling.`

### S05.4.e1 — Execution-time bail-out on claimed-leaf falsification

`When the execution impl-orchestrator observes runtime evidence that falsifies a spec-leaf the phase claimed (not merely that the code fails the test), impl-orch shall halt the fix loop for that concern, write redesign-brief.md using the execution-time sections, emit a terminal report citing the brief, and return control to dev-orchestrator.`

### S05.4.e2 — Planning-time bail-out on pre-planning contradiction

`When the planning impl-orchestrator discovers during pre-planning that runtime probes falsify a spec-leaf contract or reveal that the architecture tree's assumed structure is wrong (e.g. a leaf asserting module X is a sink but runtime data shows X is a hub), impl-orch shall write redesign-brief.md using the planning-time sections and emit a terminal report before spawning @planner, because spawning the planner against a falsified design wastes a slot and produces a plan that has to be thrown away.`

### S05.4.e3 — Planning-time bail-out on K_fail or K_probe exhaustion

`When the planning impl-orchestrator exhausts K_fail=3 or K_probe=2 per S04.3 without converging on a plan, impl-orch shall emit a planning-blocked terminal report citing redesign-brief.md with the gap reasoning from each re-spawn, and route to dev-orch for either a design revision cycle or a scope adjustment.`

### S05.4.e4 — Planning-time bail-out on structural-blocking signal

`When the planning impl-orchestrator receives a returned plan with Parallelism Posture: sequential and Cause: structural coupling preserved by design per S04.4, impl-orch shall emit a structural-blocking terminal report citing the planning-time redesign brief and shall not proceed to execution.`

### S05.4.s1 — Justification burden is non-trivial

`While the execution or planning impl-orchestrator is writing a redesign brief, the brief shall articulate why the evidence is falsification rather than fixable friction — naming specific spec-leaf IDs, quoting the EARS statements, and naming the runtime evidence that contradicts them — and a brief that cannot meet this burden shall be rejected by dev-orch per S06.1 and returned for a stronger case.`

**Reasoning.** The counterweight to a cheap bail-out mechanism is a strong defense burden. Without the burden, the hatch becomes a shortcut past hard work. With the burden, the hatch is still easy to invoke when it is warranted and easy to reject when it is not.

### S05.4.s2 — Bail-out categories that are NOT warranted

`While the execution impl-orchestrator is running the fix loop, the following shall NOT warrant escape-hatch bail-out: first-time test failures (fix and retry), fixture collateral damage (cleanup coder sweep), missing edge cases the spec already covered (generate a test from the EARS triple), missing edge cases the spec did not cover (route a scoped spec revision through dev-orch), coder mistakes a re-spawn would catch, and tester disagreements on EARS strictness (push back to dev-orch with a specific reading question).`

### S05.4.c2 — Duplicate briefs are rejected

`While dev-orch is handling a redesign brief, when the brief repeats the same falsification claim from a previous cycle without citing new evidence, dev-orch shall reject the brief per S06.3, and the rejection shall not advance the redesign cycle counter.`

### S05.4.w1 — Planning-time brief uses the Parallelism-blocking section

`Where the escape hatch fires via the planning-time arm on a structural-blocking signal, the redesign brief shall use the "Parallelism-blocking structural issues" section of redesign-brief.md, and shall name the architecture subtree and refactors.md entries the planner could not route around.`

### S05.4.s4 — Final review loop does not normally interact with the escape hatch

`While the execution impl-orchestrator is running the final review loop after all phases pass phase-level verification, the escape hatch shall not normally fire, and any final-review finding shall be either a patch-forward fix (code does not satisfy an existing leaf) or a scoped design revision (behavior exists that the spec did not anticipate); escape-hatch bail-out from the final review shall require the same justification burden as mid-execution bail-out.`

## Non-requirement edge cases

- **Severity-based hatch trigger.** An alternative would fire the hatch on severe test failures regardless of spec-leaf semantics. Rejected because it would paralyze the execution loop on normal friction. Flagged non-requirement because the epistemic trigger rule is the discipline that keeps the hatch rare enough to mean something.
- **Automatic hatch firing without brief.** An alternative would let impl-orch emit a structural-blocking terminal report without writing a brief, leaving dev-orch to reconstruct the context. Rejected because the brief is load-bearing for audit and for dev-orch's routing decision (design problem vs scope problem). Flagged non-requirement because the brief-first rule is load-bearing for hatch accountability.
- **Single unified brief file across cycles.** An alternative would append each cycle's brief to a single file. Rejected in favor of overwrite-on-cycle because cycle history lives in decisions.md and the brief is a current-cycle artifact, not a cumulative log. Flagged non-requirement to document the rejected shape.

# v3 Round-2 Convergence Report (final pass)

**Status:** converged

## Round 1 findings × final state

### r1 (alignment, gpt-5.4)

- **Source:** r1-artifact-ownership-drift
- **Finding:** terrain-contract, feasibility-questions, planner, design-orch disagreed on where parallel-cluster hypothesis and foundational prep live.
- **Final state:** aligned in `terrain-contract.md:21`, `feasibility-questions.md:45`, `design-orchestrator.md:152`, `planner.md:179` (tranche 3). Producer and consumers now point at the same three-location split (refactors.md + feasibility.md + architecture tree).
- **Verdict:** addressed

- **Source:** r1-dev-principles-gate
- **Finding:** overview inverted the yes/no logic; impl-orch carried the gate with no mechanism.
- **Final state:** D24 (decisions.md:344) + design-orchestrator.md:200 + overview.md:177-181 scope the gate to design-orch only. impl-orchestrator.md:206 carries it as a reviewer lens in the final review fan-out, not a self-check gate. overview.md:179 correctly says a "yes" answer blocks convergence.
- **Verdict:** addressed

- **Source:** r1-EARS-enforcement-contract
- **Finding:** D17 promised EARS-enforcement reviewer but operative fanout did not name one.
- **Final state:** spec reviewer is now explicitly the EARS-enforcement contract in `design-orchestrator.md:271` ("This reviewer is the EARS-enforcement contract ... PASS verdict ... every leaf checked against that grammar") and `decisions.md:260` (D17 body).
- **Verdict:** addressed

- **Source:** r1-stale-decision-text (D2/D11/D13/D14, D5 scenario-vocab leak)
- **Final state:** D2/D11/D13/D14 marked "Revised by D16-D26" with revision notes. D5 reworded ("scenario scope issues" → "spec-leaf scope mismatches"; single K=3 cap → two-counter scheme) in tranche 4. Only legitimate historical references to `scenarios/` retirement remain in D22 and the D14 revision note.
- **Verdict:** addressed

### r2 (SDD shape, opus) — BLOCKING

- **Source:** r2-dev-orch-inversion
- **Finding:** dev-orchestrator.md:15 implied architecture reading shapes acceptance criteria.
- **Final state:** `dev-orchestrator.md:15` now anchors spec production to requirements.md, with existing-code reading as context only.
- **Verdict:** addressed

- **Source:** r2-spec-first-production-order
- **Finding:** two trees could be read as produced in parallel.
- **Final state:** `design-orchestrator.md:47` makes spec-first production explicit as a convergence rule.
- **Verdict:** addressed

- **Source:** r2-EARS-mapping-overreach
- **Finding:** "parse EARS leaves directly into test triples" overreached for Ubiquitous/Optional-feature.
- **Final state:** per-pattern parsing table `design-orchestrator.md:121-133` covers all five patterns with a "cannot mechanically parse — requires design clarification" escape valve. D25 captures the rationale.
- **Verdict:** addressed

### r2 should-fix (tranche 5 scope)

- **Source:** r2-non-orchestrator-EARS-example
- **Final state:** five non-orchestrator examples (CLI subcommand, filesystem contract, config layer, harness adapter, state store) added at `design-orchestrator.md:105-111` demonstrating the notation generalizes.
- **Verdict:** addressed

- **Source:** r2-verification-notes-downgrade
- **Final state:** field 7 renamed to "Verification notes (optional)" at `design-orchestrator.md:61` with explicit "never load-bearing" language and reviewer heuristic.
- **Verdict:** addressed

- **Source:** r2-non-requirement-escape-valve
- **Final state:** spec reviewer focus area (6) at `design-orchestrator.md:271` names the escape valve audit explicitly: non-requirement without falsifiable reasoning is a convergence blocker; verification-notes-doing-EARS-work is a flag.
- **Verdict:** addressed

- **Source:** r2-root-overview-size-cap
- **Final state:** `design-orchestrator.md:86-91` invariant "Root-level invariants live in leaves, not in the overview" pushes Ubiquitous root requirements to `S00.*` leaves and root topology to `A00.*` leaves, keeping the overview as a pure TOC. Not a hard size cap but the structural mechanism that r2 named as "should-fix, future pass" is in place.
- **Verdict:** addressed

### r3 (structure/refactor, gpt-5.2)

- **Source:** r3-stale-D11-D13-decisions
- **Final state:** D11 and D13 bodies now have "Revised by D19/D20/D22" annotations and explicit revision notes; v2 mechanics retired.
- **Verdict:** addressed

- **Source:** r3-overview-three-artifact-looseness
- **Final state:** `overview.md` "Three artifact contracts" section now points at `terrain-contract.md` for contract detail instead of restating retired fields.
- **Verdict:** addressed

- **Source:** r3-terrain-two-outputs-wording
- **Final state:** `terrain-contract.md:15` reads "three locations, two first-class artifacts" consistently.
- **Verdict:** addressed

- **Source:** r3-must-land-before-phase-leak
- **Final state:** `terrain-contract.md:56` anchors `must land before` to spec leaves / architecture subtrees / refactor IDs, never phase numbers.
- **Verdict:** addressed

- **Source:** r3-coupling-witness
- **Final state:** `terrain-contract.md:55` requires a concrete coupling witness (import edge, symbol dependency, shared fixture, call chain).
- **Verdict:** addressed

- **Source:** r3-refactor-vs-foundational-prep-boundary
- **Final state:** `terrain-contract.md:206` has boundary-case rules and worked examples for classifying refactor vs foundational prep.
- **Verdict:** addressed

### r4 (decomposition sanity, sonnet) — BLOCKING + MODERATE + MINOR

- **Source:** r4-leaf-ownership-granularity (BLOCKING)
- **Finding:** leaf-file vs EARS-statement granularity ambiguous.
- **Final state:** planner (producer) at `planner.md:197`, impl-orch (consumer) at `impl-orchestrator.md:64` and `:204` (final review), dev-orch (plan review) at `dev-orchestrator.md:63`, and preservation-hint at `preservation-hint.md:39,41` all consistently validate at `S<subsystem>.<section>.<letter><number>` EARS-statement granularity. A leaf file may split its statements across phases as long as every statement has exactly one owner. Tranche 4 closed the consumer-side gap.
- **Verdict:** addressed

- **Source:** r4-EARS-parsing-gap (BLOCKING)
- **Finding:** Ubiquitous and Optional-feature patterns were not mechanically parseable.
- **Final state:** per-pattern parsing guide at `design-orchestrator.md:121-133` with five-pattern coverage + D25 captures rationale + escape valve.
- **Verdict:** addressed

- **Source:** r4-refactor-depends-on-feature (MODERATE)
- **Final state:** `terrain-contract.md:63-71` adds conditional "depends on feature" field with worked guidance; foundational prep vs refactor split lets planner sequence Round 0 (foundational) → Round 1 (refactor) → Round 2 (feature).
- **Verdict:** addressed

- **Source:** r4-K=3-exhausted-by-probe-requests (MODERATE)
- **Final state:** D12 split counter scheme (`K_fail`=3 failed plans + `K_probe`=2 probe-requests) propagated to `impl-orchestrator.md:72-82`, `planner.md:135`, `dev-orchestrator.md:46,67,74,131`, `redesign-brief.md:90`, `decisions.md:186` (D12 body), `decisions.md:101` (D5 body). Probe-requests no longer burn down the fail counter.
- **Verdict:** addressed

- **Source:** r4-preservation-cycle-leaf-carry-over (MINOR)
- **Final state:** `preservation-hint.md:120` + `planner.md:197` explicitly require the planner to copy preserved phases' EARS statement IDs from the hint into the new `plan/leaf-ownership.md` on redesign cycles.
- **Verdict:** addressed

- **Source:** r4-signal-precedence (MINOR)
- **Final state:** `impl-orchestrator.md:82`, `planner.md:145`, and `decisions.md:190` (D12 precedence paragraph) all name `structural-blocking` as winning over `planning-blocked` when both signals apply. The short-circuit bypasses both counters.
- **Verdict:** addressed

- **Source:** r4-preserved-phase-reverification (additional discovery during tranche 3)
- **Final state:** D26 (`decisions.md:366`) + `preservation-hint.md:35` sub-category + `impl-orchestrator.md:130` tester-only re-verification pass + `preserved-requires-reverification` status in `plan/status.md`. Closes the silent spec-drift surface r4 pointed at.
- **Verdict:** addressed

## p1548 findings × tranche 4/5 fix

- **p1548 finding 1:** Leaf-ownership granularity consumer-side mismatch. Planner (producer) fixed at EARS-statement granularity, but `impl-orchestrator.md:64` and `dev-orchestrator.md:63` still validated leaf-file granularity.
- **Tranche 4 fix:** Propagated EARS-statement granularity to `impl-orchestrator.md:64` (completeness check), `impl-orchestrator.md:204` (final review loop alignment check), and `dev-orchestrator.md:63` (plan review criterion 4). All three consumer-side sites now explicitly validate at `S<subsystem>.<section>.<letter><number>` granularity with the "single leaf file may split statements across phases" carve-out.
- **Verdict:** addressed

- **p1548 finding 2:** Scenario-vocabulary and K=3 sweep incomplete. Active D5 text still said "scenario scope issues" and "K=3 spawns"; dev-orchestrator.md and redesign-brief.md sites still said "K=3".
- **Tranche 4 fix:** D5 at `decisions.md:100-101` reworded to "spec-leaf scope mismatches" and the full two-counter scheme. K=3 wording replaced at `dev-orchestrator.md:46,67,74,131`, `redesign-brief.md:90`, `impl-orchestrator.md:231`. Only remaining K=3 in the design tree is `decisions.md:193` (D12's rejected-alternatives list, the legitimate "v0 K=3" historical reference).
- **Verdict:** addressed

- **p1548 paper cut:** `preservation-hint.md:39` column header stale ("Spec leaves satisfied" with EARS statement IDs underneath).
- **Tranche 4 fix:** Added column-semantics prose at `preservation-hint.md:39` and renamed column header at `preservation-hint.md:41` to "Spec leaves satisfied (EARS statement IDs)". The planner-copies-verbatim rule is stated explicitly.
- **Verdict:** addressed

## New findings introduced by tranche 4 or 5

None. Tranche 4 is a localized propagation/sweep pass with no new mechanisms — every edit resolves an earlier-stated ambiguity without creating a downstream one. Tranche 5 is scoped to `design-orchestrator.md` only (spec-leaf content field 7, EARS example set, spec-reviewer focus area 6) and its additions are self-consistent with the tranche 3 EARS contract, D25 parsing rules, and the rest of the spec-leaf template. No new contradictions, no stale references reintroduced, no cross-doc drift created.

## Convergence verdict

**converged**

Every round-1 finding (r1-r4, blocking + should-fix + minor) is addressed in the final state. Both p1548 residual propagation gaps (consumer-side leaf-ownership granularity, scenario/K=3 sweep) are fully closed by tranche 4. The tranche 4 paper cut (preservation-hint column header) is closed. Tranche 5 lands the remaining r2 should-fix items cleanly. No new blockers or structural regressions surfaced. The design package is ready for user approval and planner handoff.

## Paper cuts (non-blocking)

- `reviews/v3-round2/convergence-check-prompt.md:22` is the archived brief sent to p1548 and naturally still references "D5 scenario-vocabulary and K=3 sweep completed" in past-tense context. Audit artifact, not active design prose — safe to leave as-is.
- `impl-orchestrator.md:225` still contains the line "Scenario-based verification framing. Phases now claim spec-leaf IDs and testers verify EARS statements; the `scenarios/` convention is retired entirely." This is under the "What is removed" section (i.e., documenting the v2 → v3 delta), so the word "scenarios" is load-bearing as a historical reference. Not a propagation gap.
- decisions.md Executive Summary at line 15 still says "the 'verified scenarios' field is replaced by ..." — same category: describing the D14 → D22 delta, not active v3 contract. Leaving it explicit is fine because it tells a reader of the revision note what got replaced.
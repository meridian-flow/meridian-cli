# Round 2 Design Review — Design-Alignment Focus

Review the Round 2 design package for the orphan-run reaper fix (GH issue #14, reopened). Round 1 was rejected with 8 findings (F1-F8); Round 2 must address every one with explicit mechanism, not heuristics.

## Your focus

**Design alignment.** Does the Round 2 package actually address F1-F8 and the Round 1 reviewer findings, or does it paper over them? Call out any finding that is claimed-addressed but not actually addressed by mechanism. Verify:

1. **F1 (origin first-class)** — is origin truly a persisted field with mechanism authority, or is it inferred from `error` content anywhere outside the documented legacy shim? Is the shim scope bounded and has a deletion plan?
2. **F2 (atomic CAS)** — is `running → finalizing` actually atomic under the same flock that projects state? Are reconciler writes re-validated under the flock?
3. **F3 (depth gate coverage)** — does the gate cover **every** reconciler entrypoint including the single-row `read_spawn_row` path at `ops/spawn/query.py:70`?
4. **F4 (heartbeat evidence)** — does the probe evidence actually justify a runner-owned heartbeat, and is the 120s window safe given the observed silence gaps (153.9s Claude, 86.8s Codex)?
5. **F5 (full writer surface)** — are all 11 `finalize_spawn` writer sites enumerated and mapped to origins?
6. **F6 (consumer audit)** — is the consumer update (view_map, --status validator, stats) treated as implementation scope or deferred?
7. **F7 (decide/write split)** — does the reconciler split cleanly into pure decider + I/O shell?
8. **F8 (heartbeat helper isolable)** — is the heartbeat stat helper kept local for future evolution?

Also verify:

- **Preservation-hint adherence.** Does the revised package preserve what the preservation hint said to preserve and revise what it said to revise?
- **EARS ID stability.** Are stable IDs preserved where mechanism survives unchanged, and only renumbered/added where the mechanism materially changed?
- **Spec-architecture-refactor cross-references.** Do the spec statements cross-reference architecture and refactor entries so the contract, mechanism, and rearrangement are all traceable?

## Package contents

Everything lives under `$MERIDIAN_WORK_DIR/`:

- `decisions.md` — D-1..D-15, including the F1-F8 mapping
- `design/spec/overview.md` — EARS statements
- `design/architecture/overview.md` — mechanism (CAS protocol, origin enum, writer map, heartbeat design, depth gate topology, decide/write split)
- `design/refactors.md` — R-01..R-08 rearrangement agenda
- `design/feasibility.md` — probe evidence + F1-F8 verdicts
- `probe-heartbeat.md` — raw harness-cadence probe data
- `requirements.md` — captured intent
- `plan/preservation-hint.md` — controlling input from dev-orch
- Prior review reports: `.meridian/spawns/p1728/report.md`, `p1731/report.md`, `p1732/report.md`

## Deliverable

Your review report should:

1. Enumerate findings by severity: **Blocker** (design cannot ship), **Serious** (must fix before ship), **Nit** (fix or record-as-deferred).
2. For each finding, cite specific artifact + line/section.
3. If you conclude the package is ready to ship, say so explicitly with a reasoned verdict.
4. No hedging. Call mechanism failures failures; call hand-waving hand-waving.

Return a terminal report via the standard report mechanism.

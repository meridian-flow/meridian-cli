# Round 2 Design Review — Structural Soundness Focus

Review the Round 2 design package for the orphan-run reaper fix (GH issue #14, reopened). Round 1 was rejected for using heuristics where mechanism was required. Round 2 adds a first-class origin field, atomic CAS for `running → finalizing`, runner-owned heartbeat, and a decide/write split.

## Your focus

**Structural soundness.** Is the mechanism actually correct and coherent? Look for:

1. **Concurrency correctness.** Walk the CAS protocol. Is `mark_finalizing` race-free under `spawns.jsonl.flock`? Can two writers corrupt the log? Does the reconciler re-validation actually close the race described in F2? What happens on CAS miss when the runner proceeds?
2. **Projection authority rule.** Is the "authoritative supersedes reconciler" rule airtight? Can an adversarial event stream produce an inconsistent terminal state? What does `terminal_origin` look like after an authoritative-over-reconciler supersede — is metadata merging consistent?
3. **Lifecycle invariants.** Is `finalizing` truly non-terminal? Is `queued → finalizing` genuinely disallowed? Does the projection's "late `SpawnUpdateEvent.status` never downgrades terminal" invariant actually hold under all event orderings?
4. **Writer surface completeness.** Cross-check the 11-writer map against the repo. Are any writers missing? Is every writer's origin label epistemically correct?
5. **Reaper correctness.** Is the heartbeat window safe for `finalizing`? Is the decide/write split decision ADT complete (Skip, FinalizeFailed, FinalizeSucceeded)? Are edge cases enumerated (heartbeat artifact missing, report.md present but runner still alive, etc.)?
6. **Heartbeat design.** Is a 30s tick with 120s window actually robust against scheduling jitter, GC pauses, and blocking I/O in the runner's event loop? Is the task lifecycle (start on `running`, stop after terminal `finalize_spawn`) correct under all abnormal-exit paths?
7. **Legacy shim correctness.** Does `resolve_finalize_origin` correctly classify every legacy event? Is `LEGACY_RECONCILER_ERRORS` complete? Is the removal window (6 weeks) defensible?
8. **Edge cases.** Look for missing edge cases: what if `heartbeat` mtime advances after terminal? What if `mark_finalizing` returns True but the runner crashes before any heartbeat tick? What if the reconciler guard fires and projection picks up a late authoritative finalize — is metadata intact?

## Package contents

Everything lives under `$MERIDIAN_WORK_DIR/`:

- `decisions.md` — D-1..D-15, including the F1-F8 mapping
- `design/spec/overview.md` — EARS statements
- `design/architecture/overview.md` — mechanism (CAS protocol, origin enum, writer map, heartbeat design, depth gate topology, decide/write split)
- `design/refactors.md` — R-01..R-08 rearrangement agenda
- `design/feasibility.md` — probe evidence + F1-F8 verdicts
- `probe-heartbeat.md` — raw harness-cadence probe data
- `arch-cas-memo.md`, `arch-origin-memo.md` — architect memos
- `plan/preservation-hint.md` — controlling input from dev-orch
- Source files (read-only reference): `src/meridian/lib/state/spawn_store.py`, `reaper.py`, `lib/core/spawn_lifecycle.py`, `lib/launch/runner.py`, `lib/launch/streaming_runner.py`

## Deliverable

Your review report should:

1. Enumerate findings by severity: **Blocker**, **Serious**, **Nit**.
2. For each finding, cite specific artifact + section, and when possible, walk through the failure scenario concretely.
3. If you find none, say so explicitly — do not invent issues.
4. Focus on structural soundness; leave nit-picks on wording to other reviewers.

Return a terminal report via the standard report mechanism.

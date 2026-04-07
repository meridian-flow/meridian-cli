# Staffing

Recommended team composition per phase. Coders default to
`gpt-5.3-codex` per project convention (see CLAUDE.md). Reviews fan out
across strong models with different focus areas.

## Per-phase coder assignments

| Phase | Coder                        | Parallelizable? |
|-------|------------------------------|-----------------|
| 0     | one coder (deletions only)   | no (blocks 1)   |
| 1     | one coder (tiny)             | no              |
| 2     | one coder (load-bearing)     | no (blocks 3/4) |
| 3     | one coder                    | parallel w/ 4   |
| 4     | one coder                    | parallel w/ 3   |
| 5     | one coder (tests)            | no              |
| 6     | one coder (meridian-channel) | no              |

Phases 3 and 4 can be handed to two coder spawns at the same time once
phase 2 is merged — they touch disjoint files (`cli/models.rs` +
`cli/sync.rs`+`sync/mod.rs`).

## Reviewer fan-out

Reviews run after each phase's coder completes. Convergence (not a fixed
pass count) decides when to move on.

### Phase 0 (scoped dead-code sweep — low risk, safety-gated)

Runs as three sub-steps, not a single coder pass. See
`phase-0-dead-code-sweep.md`.

- **Step 0.1 — `refactor-reviewer` (default model).** Read-only sweep
  across the six in-scope files. Brief: identify dead code, unused
  helpers, stale comments, dead branches, unreferenced types, leftover
  scaffolding. Deletion candidates only — no new abstractions.
- **Step 0.2 — `coder` (gpt-5.3-codex).** Applies the deletions (and
  trivial inlining only). Constrained to deletions-only, no behavioral
  changes, no files outside the in-scope list.
- **Step 0.3 — reviewer fan-out (parallel, default model + opus).**
    - **default model** — focus: "safe to delete given P1-P6 will need
      these files." Passed the refactor findings, the coder diff, and
      every downstream phase blueprint. Checks that no deletion removes
      something the feature phases were going to import or extend.
    - **opus** — focus: "design alignment with the dead-code-only
      constraint." Passed the coder diff and `phase-0-dead-code-sweep.md`.
      Checks nothing crept in that's actually a refactor.

Two reviewers is right-sized for a low-risk deletions-only phase where
the primary risk is "accidentally deleted something P1-P6 needed." The
default-model reviewer owns the cross-phase safety check; opus owns the
scope-envelope check. Convergence as usual.

### Phase 1 (small — low risk)

- 1 reviewer, default model. Focus: **correctness of serde default** and
  that `Settings::default()` matches.

### Phase 2 (load-bearing helper — high risk)

- **gpt-5.4** — focus: concurrency correctness (double-check under lock,
  re-read-under-lock pattern, MARS_OFFLINE precedence).
- **gpt-5.2** — focus: error-path completeness (every branch of
  `RefreshOutcome` exercised, `ModelCacheUnavailable` reasons are
  correct, stale-vs-empty distinction upheld).
- **opus** — focus: API design and maintainability (is `ensure_fresh_
  with` seam right, signature stable for downstream phases, naming).
- **opus** — focus: design alignment, passed
  `design/ensure-fresh.md` + `design/concurrency.md`.

Four reviewers because this helper is the lynchpin; if it ships buggy,
phases 3-6 build on sand.

### Phase 3 (CLI wire-up — medium risk)

- **gpt-5.4** — focus: flag plumbing, JSON output stability, no
  backward-incompat surprises.
- **opus** — focus: design alignment against `design/call-sites.md`.
- **default** — focus: error message UX, stderr vs stdout, JSON vs
  non-JSON symmetry.

### Phase 4 (sync wire-up — medium risk)

- **gpt-5.4** — focus: "sync never aborts on refresh failure" invariant,
  `dry_run` path untouched, diag warn wiring.
- **opus** — focus: design alignment against `design/call-sites.md` §1.
- **default** — focus: scanning for missed `SyncOptions` construction
  sites.

### Phase 5 (tests — low risk but broad)

- **gpt-5.2** — focus: coverage gaps against the requirements success
  criteria.
- **default** — focus: test hermeticity (no real network, no shared
  global state).

### Phase 6 (meridian follow-up — low risk)

- 2 reviewers, default model, split focus: one on the timeout rationale
  + smoke markdown, one on design alignment against
  `design/meridian-integration.md`.

## Model diversity rationale

- **gpt-5.4** pulls on concurrency/invariant work (phase 2 + 4); strong
  on low-level correctness.
- **gpt-5.2** pulls on exhaustive case enumeration (phase 2 errors +
  phase 5 coverage).
- **opus** pulls on design-alignment and API-shape reviews — it's used
  as the project documenter and carries project context well.
- **default** fills baseline coverage everywhere else.

Run `meridian models list` before kicking off to confirm the exact
aliases available in the project.

## Decision-review

The orchestrator should itself request a review of this staffing plan
before starting phase 2 coder work — phase 2 is the load-bearing phase
and any staffing miscalibration there compounds. One opus reviewer with
focus: "phase 2 has enough coverage; phase 2 reviewer briefs are
non-redundant".

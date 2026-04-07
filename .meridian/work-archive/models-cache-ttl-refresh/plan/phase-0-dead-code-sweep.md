# Phase 0: Scoped Dead-Code Sweep

**Repo:** mars-agents (`../mars-agents/`) + meridian-channel
**Depends on:** nothing
**Blocks:** Phase 1 (and by extension every downstream phase)
**Est. size:** deletions only — expect net-negative LoC

## Goal

Produce a clean baseline on the exact files Phases 1-6 will touch, so the
feature diffs for the TTL refresh work aren't muddied by refactor noise
(dead helpers, unused types, stale comments, leftover scaffolding from
prior refactors). This phase removes code only — no new abstractions,
no behavioral changes, no moves that aren't trivial inlining.

The sweep is **intentionally scoped** to the files the feature work will
edit. A broader cleanup across both repos is a separate follow-up work
item (see decisions.md D10).

## In-Scope Files

**mars-agents (`../mars-agents/`):**

- `src/models/mod.rs`
- `src/cli/models.rs`
- `src/cli/sync.rs`
- `src/sync/mod.rs`

**meridian-channel:**

- `src/meridian/lib/catalog/model_aliases.py`
- `src/meridian/lib/catalog/models.py`

Do not touch any file outside this list, even if dead code is spotted in
neighbors — log it as a follow-up instead.

## Workflow

This phase runs as three sequential sub-steps, not a single coder pass:

### Step 0.1 — Refactor-reviewer sweep (read-only)

Spawn a `refactor-reviewer` against the six files above with the
explicit brief:

> Identify dead code, unused helpers, stale comments, dead match arms
> or branches, unreferenced types/structs/enums, and leftover scaffolding
> from prior refactors. Report each finding with file + line range and a
> one-line justification for why it's safe to delete. Do not recommend
> new abstractions, renames, or behavioral changes. Deletion candidates
> only.

Output: a findings list the coder will work from in step 0.2.

### Step 0.2 — Coder applies deletions

Spawn one `coder` (gpt-5.3-codex per project convention) with the
findings list from step 0.1. Constraints:

- **Deletions only.** Remove unused items. Trivial inlining (e.g.
  collapsing a one-call-site helper whose body is two lines) is allowed
  when it reduces surface area; anything more invasive is out of scope.
- **No new abstractions.** Do not introduce traits, modules, or helpers.
- **No behavioral changes.** Public APIs observable from outside the
  file set must be byte-identical in behavior. If a deletion would
  change observable behavior, skip it and flag it for the reviewer.
- **No reformatting-only churn** beyond what `cargo fmt` / `ruff` would
  auto-apply.
- If a finding is ambiguous ("is this actually unused?"), leave it and
  record it in the coder's report for the step 0.3 reviewers to
  adjudicate.

Verification the coder runs before handoff:

- `cargo fmt && cargo clippy --all-targets -- -D warnings` (mars-agents)
- `cargo test --package mars-agents` (mars-agents)
- `uv run ruff check .` (meridian-channel)
- `uv run pyright` (meridian-channel, must be 0 errors)
- `uv run pytest-llm` (meridian-channel)

### Step 0.3 — Reviewer fan-out (safety check)

Two reviewers, running in parallel, focused on **"is each deletion safe
given that Phases 1-6 are about to touch these same files?"** Not a
general code review — a targeted safety check.

- **default model** — focus: "safe to delete given P1-P6 will need
  these files." Reviewer is handed the step 0.1 findings list, the
  coder's diff, and `phase-1-config.md` through `phase-6-meridian.md`.
  Question to answer: does any deletion remove something the downstream
  phases were going to import, call, extend, or pattern-match on?
- **opus** — focus: "design alignment with the dead-code-only
  constraint." Reviewer is handed the coder's diff and this blueprint.
  Question to answer: did the coder stay inside the deletion-only
  envelope, or did anything sneak in that's actually a refactor?

Review loop runs until convergence (no new substantive findings). If a
reviewer flags a deletion as unsafe, the coder reverts that specific
deletion and reruns verification.

## Interface Contract

None added, none removed (by design — this phase preserves all
externally-observable behavior). If the sweep discovers that an
"externally observable" symbol is in fact unused across the whole
workspace, it may be deleted; otherwise it stays.

## Dependencies

- Requires: nothing
- Produces: a clean baseline on the six in-scope files
- Independent of: every other phase (but blocks them)

## Verification Criteria

- [ ] Refactor-reviewer findings list exists and every item is either
      applied, deferred-with-reason, or rejected-with-reason.
- [ ] `cargo fmt && cargo clippy --all-targets -- -D warnings` passes in
      `../mars-agents/`.
- [ ] `cargo test --package mars-agents` passes in `../mars-agents/`.
- [ ] `uv run ruff check .` passes in meridian-channel.
- [ ] `uv run pyright` reports 0 errors in meridian-channel.
- [ ] `uv run pytest-llm` passes in meridian-channel.
- [ ] Net diff on the six in-scope files is non-positive LoC (deletions
      may be offset by import-line cleanups but must not grow).
- [ ] No file outside the in-scope list is modified.
- [ ] Reviewer fan-out (default + opus) converges clean.

## Out of Scope

- Any file not listed under "In-Scope Files."
- Renames, extractions, moves, or new helpers.
- Cross-repo dead code in modules Phase 1-6 don't touch (queued as a
  follow-up work item per decisions.md D10).
- Behavioral changes, even "obviously correct" ones — those go through
  a normal feature phase, not a sweep.
- Comment rewrites that aren't stale-comment deletion.

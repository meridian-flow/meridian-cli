# Test Suite Cleanup + Strictness Plan

Date added: 2026-03-07
Status: `proposed`
Priority: `high`

## Goal

Delete the slice-era test suite, keep only automated coverage for Meridian's
core invariants, replace the remaining coverage with a smaller subsystem-based
suite, shrink smoke verification to a short operator workflow, and finish with a
`pyright`-clean strict codebase.

## Why This Matters

The current suite is dominated by implementation-history files rather than a
clear verification strategy. The problem is not just naming. The bigger issue is
that too many tests pin intermediate shapes, duplicated command-surface details,
or past slice boundaries that no longer matter.

That creates four kinds of drag:

- the suite is larger than the protection it actually provides
- it is unclear which tests encode product invariants versus historical scaffolding
- refactors pay a high tax for low-value assertions
- `pyright` cleanup is harder because verification tiers are not cleanly defined

## Principles

1. Default to deleting old tests, not preserving them.
2. Keep automated coverage for invariants, not for implementation history.
3. Rewrite surviving coverage from scratch by subsystem when that is simpler than merging old files.
4. Treat smoke as operator confidence only, not as a substitute for invariant coverage.
5. Do not start broad pyright cleanup until the new test gate is stable.
6. Commit after each passing slice.

## Target End State

### Automated gate (`uv run pytest-llm`)

A materially smaller suite that protects:

- config precedence, parsing, and validation
- model alias/catalog filtering, resolution, and suggestion behavior
- file-authoritative state invariants: ids, append/replay, locking, session/spawn persistence
- explicit-space and session/space lifecycle invariants
- minimal harness command/extraction invariants that are pure and cheap, including parser/fallback behavior
- spawn execution lifecycle with mock harness: success, retry, timeout, cancel, finalization, and signal/finalization race safety
- prompt assembly and reference isolation
- permission/environment filtering and safety wiring

### Smoke gate

A short workflow for:

- `meridian --help`, `--version`, `skills list`, `doctor`, `config init`
- one or two end-to-end primary/spawn flows with the mock harness
- top-level output-format sanity only

### Structure

Any remaining automated tests should live under subsystem directories such as:

- `tests/config/`
- `tests/state/`
- `tests/space/`
- `tests/harness/`
- `tests/prompt/`
- `tests/exec/`
- `tests/ops/`
- `tests/smoke/` only if a very small smoke subset remains pytest-based

No planning scratch or "important tests" notes should live under `tests/`.

### Type quality

- `uv run pyright` passes with zero errors
- strict typing cleanup is complete
- dead code and stale compatibility shims discovered during pyright cleanup are removed

## Orchestration Model

This work should run as a sequenced orchestration plan, not a one-shot rewrite.

Recommended supervisor loop:

1. inventory current tests by invariant, not by file preservation
2. choose one subsystem or verification tier slice
3. write the replacement tests for that slice
4. delete the old slice-era files covered by the replacement
5. run the minimum relevant pytest subset and `pyright` if type-affecting
6. commit
7. continue

Suggested agent roles:

- research/review agent: identify actual invariants and low-value legacy assertions
- implementation agent: write new subsystem tests and delete replaced files
- review agent: verify that deletion did not drop core coverage

## Phase Plan

### Phase 1: Invariant Inventory

Produce a canonical map of the current suite in terms of:

- `keep-automated`
- `move-to-smoke`
- `delete`
- `rewrite-as-new-suite`

Rules:

- inventory by invariant first, files second
- do not assume existing files survive
- call out backward-compat-only tests for immediate deletion
- store notes under `scratch/` or `plans/`, not under `tests/`

Deliverables:

- a short written inventory of what must remain automated
- a delete list for slice-era files and compatibility-only checks to remove immediately
- a proposed replacement subsystem layout

Verification:

- no code changes required beyond inventory notes

Commit checkpoint:

- "Inventory invariants and delete targets for test rewrite"

### Phase 2: Rebuild Config/State/Space Core

Write new subsystem tests from scratch for the core file-authoritative layer:

- config precedence and validation
- id generation and path/state-root resolution
- spawn/session store replay and locking
- explicit-space requirements and space/session lifecycle

Then delete the old files those new tests replace.

Rules:

- prefer new clean files over renaming old ones
- keep helpers only when they genuinely reduce duplication
- remove replaced slice-era files in the same slice once coverage is clearly superseded

Verification:

- targeted pytest for `tests/config/`, `tests/state/`, and `tests/space/`
- collection remains clean

Commit checkpoint:

- "Rewrite config state and space tests around core invariants"

### Phase 3: Rebuild Harness/Prompt/Exec Core

Write new subsystem tests from scratch for:

- harness command-building/extraction sanity
- materialization/cleanup semantics
- prompt assembly and launch resolution
- execution retry/timeout/cancel/finalize behavior
- safety/environment filtering

Then delete the replaced slice-era files.

Verification:

- targeted pytest for `tests/harness/`, `tests/prompt/`, and `tests/exec/`
- whole curated pytest gate still passes

Commit checkpoint:

- "Rewrite harness prompt and exec tests around core invariants"

### Phase 4: Delete Residual Low-Value Tests

Delete the remaining tests that only prove:

- CLI help text and command-shape duplication
- command registration-shape duplication
- backward-compat behavior the repo no longer needs to preserve
- historical slice-specific behavior with no current product value
- plumbing already covered by deeper op-layer or lifecycle tests

Move any operator-confidence checks that still matter into the smoke workflow.

Deliverables:

- smaller pytest suite
- explicit delete record for removed legacy files
- smoke guidance updated to absorb any retained operator checks

Verification:

- targeted pytest for touched subsystems
- `uv run pytest-llm` passes

Commit checkpoint:

- "Delete residual low-value tests and separate smoke coverage"

### Phase 5: Smoke Path Cleanup

Rewrite `tests/SMOKE_TESTING.md` into a short deliberate workflow.

Options:

- keep it as markdown with fewer checks
- replace part of it with a small script plus markdown wrapper
- keep only a tiny pytest smoke subset if clearly stable and useful

Verification:

- smoke commands run cleanly in a fresh temp repo using the mock harness

Commit checkpoint:

- "Simplify smoke verification workflow"

### Phase 6: Strict Pyright Cleanup

Only after the new test gate is stable:

- run `uv run pyright`
- fix all type errors
- remove weak typing surfaces and dead paths revealed by pyright
- avoid unrelated architectural churn

Verification:

- `uv run pyright`
- targeted pytest for touched subsystems

Commit checkpoint:

- "Make codebase pyright-clean under strict typing"

### Phase 7: Final Gate Cleanup

Establish the final expected developer loop:

- `uv run pytest-llm`
- `uv run pyright`
- optional curated smoke pass before releases or major refactors

Deliverables:

- docs updated in README/dev docs
- obsolete test guidance removed
- final gate commands made explicit

Verification:

- `uv run pytest-llm` passes
- `uv run pyright` passes

Commit checkpoint:

- "Document final verification gates"

## Slice Breakdown

Recommended slices:

1. Inventory invariants, delete targets, and replacement layout.
2. Rewrite config tests and delete replaced config slice files.
3. Rewrite state/space tests and delete replaced state/space slice files.
4. Rewrite harness/prompt tests and delete replaced harness/prompt slice files.
5. Rewrite exec/safety tests and delete replaced exec slice files.
6. Delete residual low-value tests and shrink smoke.
7. Run pyright cleanup for config/state/space code.
8. Run pyright cleanup for harness/prompt/exec/ops code.
9. Final docs and verification gate cleanup.

## What Must Stay Automated

These areas are too core to demote to manual smoke:

- config precedence and env override behavior
- explicit-space requirement behavior
- ID generation and JSONL append/replay behavior
- session locking and stale cleanup
- spawn finalization, retry classification, timeout, and cancellation behavior
- minimal harness command building and session/report extraction invariants
- materialization and cleanup semantics
- prompt assembly and reference isolation
- permission/safety environment filtering

## What Can Move Out of Core Pytest

Candidates for smoke or deletion if redundant:

- repeated `--help` and surface-listing checks
- repeated "returns JSON with key X" command-shape tests
- high-level CLI walkthroughs already covered by deeper lifecycle tests
- broad command tours better expressed as smoke scripts/checklists

## Risks

1. Deleting aggressively can remove the only coverage for an invariant if the replacement suite is not written first.
2. Partial rewrites can leave both old and new suites active, creating duplication and confusion.
3. Pyright cleanup can sprawl into redesign work if the replacement test gate is not already trustworthy.
4. Smoke can become too weak if operator checks are moved without curation.

## Risk Controls

1. Inventory invariants before deletion.
2. Replace one subsystem at a time, then delete the superseded legacy files in the same slice.
3. Keep changes slice-sized and commit after each passing checkpoint.
4. Require review over each delete set before large removals.

## Exit Criteria

The plan is complete when:

- the old slice-era test structure is gone
- the automated suite is materially smaller and easier to reason about
- surviving tests are organized by subsystem and protect only core invariants
- smoke verification is shorter and explicitly scoped
- `uv run pytest-llm` passes
- `uv run pyright` passes with zero errors
- docs describe the intended verification workflow clearly

---
name: dev-principles
description: Engineering principles LLM agents systematically violate — refactoring discipline, abstraction judgment, deletion courage, and structural hygiene. Loaded into orchestrators to trigger proactive refactoring and into reviewers to guide what to flag.
---

# Refactor Early, Refactor Continuously

- Run `refactor-reviewer` at every phase boundary, not only when things feel wrong.
- Act on refactor findings in the current phase; do not defer structural fixes.
- Perform preparatory refactoring before feature work; make the change easy, then make the easy change.
- Keep refactoring and feature commits separate; do not wear both hats in one commit.
- Treat declining refactor rates as a primary risk signal: refactored lines dropped from 24% to 9.5% in AI-assisted workflows.

# Abstraction Judgment

- Leave two similar cases duplicated; do not abstract yet.
- Extract an abstraction at three or more genuine instances of the same semantic pattern.
- Distinguish surface similarity from semantic similarity; similar shape does not imply shared behavior.
- Treat added parameters or branching in an abstraction as a wrong-abstraction signal.
- Fix wrong abstractions immediately: inline, delete, and let the right pattern re-emerge.
- Apply DRY aggressively to utilities (parsing, formatting, validation) and cautiously to business logic.

# Delete Aggressively

- Bias toward deletion when code has no clear active purpose.
- Remove dead code, unused abstractions, speculative features, and unrequested helpers.
- Investigate behavior not covered by tests before deleting; untested paths may still carry edge-case handling.
- Challenge preserved code that lacks a clear reason to exist.

# Follow Existing Patterns

- Read the surrounding code before implementation and match existing conventions.
- Reuse established patterns for solved problems, even if you would design differently from scratch.
- Avoid introducing new idioms for routine tasks; each novel pattern increases maintenance cost.
- Prefer consistency and predictability over cleverness.

# Structural Health Signals

Treat each signal as an immediate action trigger, not backlog material:

- Module exceeds 500 lines or holds more than three responsibilities.
- Import list growth indicates rising coupling.
- Adding one variant requires edits in five or more files.
- An abstraction accumulates conditionals to fit new cases.
- Greppability drops due to dynamic dispatch, metaprogramming, or computed names.

# Chesterton's Fence

- Understand why code exists before removing it.
- Treat `HACK` and `WORKAROUND` comments as fence markers; investigate root cause before deletion.
- Do not assume generated structure is meaningful; verify intent explicitly.
- Investigate uncertainty rather than preserving or deleting blindly.

# For Orchestrators

## Never Write Code Directly

Orchestrators coordinate — they never write code or edit source files, regardless of how trivial the change seems. This isn't ceremony for its own sake:

- **Spawns produce artifacts.** A coder spawn generates a traceable report, changed file list, and session transcript. Direct edits via Bash leave no trail — if something breaks downstream, there's nothing to inspect.
- **Review catches what the author can't see.** Even a one-line change can have unintended consequences. The orchestrator that wrote the code can't objectively review it — the same blind spot that let the bug through will let it pass review.
- **Workarounds compound.** When Edit/Write are blocked, writing files via `Bash(cat >)` or `python3 -c` bypasses the restriction without removing the reason it exists. Each workaround teaches the next session that the rules are negotiable.

If a task is too trivial for a full impl-orchestrator cycle, the dev-orchestrator should spawn a coder + reviewer directly — not hand it to an impl-orchestrator that shortcuts the process.

## Refactor Continuously

The `refactor-reviewer -> coder` loop is mandatory and immediate:

- Run `refactor-reviewer` after every feature phase.
- Resolve structural findings before starting the next phase.
- If structural debt is flagged, fix it now rather than deferring.
- Maintain structural health proactively; reactive refactors are slower and riskier.

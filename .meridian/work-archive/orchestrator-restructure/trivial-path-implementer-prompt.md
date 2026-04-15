# Two narrow fixes to meridian-dev-workflow

Two small corrections to the v3 rewrite of `meridian-dev-workflow/`. Both are scoped to the dev-orchestrator body plus one skill, and both address the same underlying pattern: overspecification where judgment should apply.

## Fix 1: Generalize "@coder" locks on the trivial/direct path

A few places in meridian-dev-workflow say "spawn `@coder`" as the direct/trivial path when the actual implementer depends on the task shape. Small work might call for `@coder`, but it might also call for `@frontend-coder` (UI work), `@code-documenter` or `@tech-writer` (docs-only changes), `@investigator` (issue triage), and so on. The dev-orchestrator picks the subagent by task shape; the prompt should reflect that rather than hardcoding `@coder`.

## Files to update

- `meridian-dev-workflow/agents/dev-orchestrator.md` — two lines:
  - Around line 46: "Typo fix or one-line config tweak: usually direct `@coder` plus tester/reviewer lanes."
  - Around line 62: "**Trivial path:** spawn `@coder` + verification lanes directly. Skip design-orch, impl-orch, and planner."
- `meridian-dev-workflow/skills/dev-principles/SKILL.md` — the line in the orchestrator section: "If a task is too trivial for a full @impl-orchestrator cycle, the @dev-orchestrator should spawn a @coder + @verifier directly, adding @smoke-tester or @unit-tester as warranted..."

## Shape of the fix

Replace hardcoded `@coder` with language that names the right implementer as a function of task shape, using concrete examples rather than exhaustive enumeration. The goal: the dev-orch reads this and understands it should pick the subagent that fits the task, with `@coder` as one common option among several.

Example shape:

> **Trivial path:** spawn the appropriate implementer (e.g. `@coder` for code, `@frontend-coder` for UI work, `@code-documenter` or `@tech-writer` for docs-only changes) with verification lanes directly. Skip design-orch, impl-orch, and planner.

The examples are illustrative, not exhaustive — the dev-orch can extrapolate to cases not named (e.g. `@verifier` for pure test additions, `@investigator` for issue triage).

Apply the same shape to the "typo fix or one-line config tweak" anchor in dev-orchestrator.md and to the dev-principles skill line.

## Leave alone

- `agents/verifier.md` line 15 ("beyond the @coder's stated checks") — this is a role-name-placeholder for whatever coder produced the work, not a lock-in. Leave as-is.
- Other `@coder` mentions that refer to a specific phase coder or to the coder role generically. Only update the hardcoded trivial/direct-path locks.

## Quality bar

- The fix preserves the intent (direct implementer spawn without orchestration overhead for small work) while generalizing the agent choice.
- The three lines flagged above are updated; no other lines are touched unless you find an equivalent hardcoding elsewhere (flag in the terminal report if so).
- `git -C meridian-dev-workflow diff --check` clean after the edit.

## Fix 2: Drop `design/refactors.md` and `design/feasibility.md` from the dev-orch approval walk

The current `agents/dev-orchestrator.md` body walks the user through `design/spec/overview.md`, `design/architecture/overview.md`, and `design/refactors.md` during the design-approval checkpoint, and says to load `design/feasibility.md` on demand. Both references belong out of the approval walk.

Reasoning:

- **`refactors.md`** is consumed by the planner as a decomposition input — it tells the planner how to sequence structural work so feature phases can parallelize. It's an internal orchestration handoff, not a user-approval surface. If the refactor agenda follows from the architecture (which it should), the user approving the architecture implicitly approves the refactors. Walking them separately asks the user to approve a planning concern, which is the wrong altitude for the approval checkpoint.
- **`feasibility.md`** is probe evidence and fix-or-preserve verdicts — it grounds design choices in runtime observations. That's an audit surface ("does this design rest on real evidence?"), not an approval surface ("does this design do what I want?"). Offering it on demand during approval mixes audit into the approval checkpoint when the two concerns serve different readers.

The clean approval walk is **spec overview + architecture overview** — the two things that answer "is this doing what you want and is it structured reasonably?" Refactors and feasibility stay as first-class artifacts for their downstream consumers but don't appear in the user-facing approval walk.

Update `agents/dev-orchestrator.md` so the approval walk section lists spec overview and architecture overview only. Remove the `design/refactors.md` bullet and remove the `Load design/feasibility.md on demand when the user asks for probe evidence or unresolved assumptions` line.

Scan the rest of the file for any other references to refactors.md or feasibility.md in the approval walk context. If dev-orch mentions them in other contexts (e.g., routing design-orch feedback or handing them to planning impl-orch via `-f`), those are legitimate — leave them alone. Only the approval walk surface is wrong.

## Return

Terminal report listing:
- The exact before/after for each line touched
- Any additional hardcoded `@coder` locks you found that should also be generalized but weren't in the flagged list
- Any references to refactors.md or feasibility.md that you weren't sure belonged in the approval walk vs elsewhere — flag for review

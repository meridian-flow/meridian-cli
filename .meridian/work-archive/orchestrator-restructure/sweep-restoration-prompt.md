# Restore standing principles lost in the p1561 sweep

A prior sweep spawn (p1561) removed "never / do not" prohibitions from `meridian-dev-workflow/` agent profiles and skills. The sweep was supposed to target only residues of v3 direction changes (e.g., "never spawn `@planner` directly", "Do not use `scenarios/`") but went broader — it also stripped long-standing behavioral principles that predate v3 and belong in the agent bodies regardless of which workflow version is in use.

Restore the standing principles the sweep removed, while keeping the v3-direction-change removals intact and preserving the v3 positive framings that came in via an earlier rewrite spawn (p1559).

## Reference state

The pre-sweep-and-rewrite baseline is `HEAD` of the `meridian-dev-workflow/` submodule. Read each affected file via `git -C meridian-dev-workflow show HEAD:<path>` to see what existed before any v3 work started. The standing principles that deserve restoration existed in that baseline.

Current working-tree state is `HEAD + p1559 rewrite + p1561 sweep` — v3 body structure, but standing principles stripped. The restoration target is "current state + the standing principles put back in a way that fits the v3 body."

## Standing principles to restore

These existed in `HEAD`, were preserved by p1559's v3 rewrite, and were stripped by p1561's sweep. They are load-bearing behavioral constraints, not v3 direction changes.

### `agents/dev-orchestrator.md`

- **Orchestrator-coordinates-not-implements** with its *why*: the altitude explanation — dropping into implementation costs the ability to catch drift from what the user wanted. The reasoning matters as much as the rule. This is the `"you don't write code or edit source files — not because of an arbitrary rule"` passage in HEAD.
- **`<do_not_act_before_instructions>` block**: the user-confirmation gate that prevents dev-orch from spawning design/impl orchestrators before the user has confirmed a direction, with the "default to research and recommendations when intent is ambiguous" reasoning.
- **Meridian-spawn-over-Agent-tool boilerplate**: the standing rule that spawned work goes through `meridian spawn` because spawns persist reports, enable model routing, and are inspectable. Built-in Agent tools lack these properties.
- **"How You Engage" craft**: active clarifying questions, pushback when something seems off, forming a view with reasoning instead of asking "what would you like to do?", clarifying scope/constraints/success-criteria before committing to a direction.
- **"Match Process to Problem" scaling anchors**: the judgment that not every task needs full design exploration and not every task can skip it, with concrete anchors (typo fix → coder + reviewer; new feature → design → plan → impl; system redesign → multiple design rounds) framed as illustrative shapes rather than a checklist.

### `agents/impl-orchestrator.md`

- **"Never write code or edit source files directly — always delegate to a `@coder` spawn"** with the reasoning that Edit/Write are intentionally disabled and the explicit rejection of working around the disable via Bash (`cat >`, `python3 -c`, heredocs).
- **Meridian-spawn-over-Agent-tool boilerplate**: same standing rule as dev-orch.
- **Concurrent-work-tree safety**: "Other agents or humans may be editing the same repo simultaneously. Treat the working tree as shared space. Never revert changes you didn't make — if you see unfamiliar changes, they're almost certainly someone else's intentional work." Plus the guidance to stage files your spawns actually modified via `meridian spawn files <id>`, and the escalation path for overlapping uncommitted work.

### `agents/design-orchestrator.md`

Scan the HEAD version and current state. Restore anything that fits the "standing behavioral principle not specific to v3" pattern — likely the meridian-spawn boilerplate and any orchestrator-coordinates-not-implements language that was present.

### `agents/planner.md`

Scan and restore similarly. Planner may have had meridian-spawn boilerplate or coordination-vs-implementation language worth keeping.

### `skills/planning/SKILL.md`

- **"Thoroughness is Mandatory" section**: the full reasoning about walking every decision entry, edge case, and audit finding into a concrete phase. The test of thoroughness (every numbered decision points at the exact phase; every edge case points at the exact verification) and the "thorough planning is expensive, do it anyway" framing.
- **"Staffing is mandatory output" section**: the three-part staffing contract — per-phase teams, final review loop, escalation policy — with the warning that a plan without staffing causes impl-orch to run @coders only without review loops.
- **"Phase Decomposition" craft**: the three phase-quality criteria (independently testable as the most important, bounded to specific files, right-sized so a single @coder can complete in one session). The plan-as-delta framing (plan describes what changes from current code, not a restatement of the target state).

### `skills/dev-artifacts/SKILL.md`

The v3 rewrite + sweep may have stripped substantive artifact-convention content that isn't specific to v3. Scan the HEAD version and restore anything that was load-bearing general craft about artifact placement, commit hygiene for work artifacts, or convention across domain boundaries.

### `skills/smoke-test/SKILL.md`, `unit-test/SKILL.md`, `verification/SKILL.md`

Scan each. Restore standing testing craft that isn't v3-specific — e.g., test-planning guidance, fixture discipline, smoke-vs-unit boundary rules, anything that survived in HEAD and got stripped.

## What to leave removed

These are the v3-direction-change residues that p1561 correctly removed. They should stay removed:

- Any variant of "never spawn `@planner` directly" — planning impl-orch owns the planner spawn, and the positive delegation chain captures this without a prohibition.
- Any variant of "do not use `scenarios/`" or "scenarios is retired and must not be produced" — the scenarios convention is retired entirely, mention nothing about it.
- Any variant of "not a separate gate" on `dev-principles` — the positive "shared operating guidance" framing handles this; the "not a gate" clause primes the rejected pattern.
- Any variant of "do not invent new refactor entries" on planner — the positive "sequence the agenda design identified" framing is sufficient.
- Any variant of "do not resume planning impl-orch for execution" — the positive "fresh execution impl-orch spawn" is sufficient.
- "Never mix both roles in one spawn" on impl-orch — the positive role-specific framing is sufficient.
- "Do not re-run probes already in feasibility.md" — the positive "read feasibility.md as input" is sufficient.

## Integration guidance

The standing principles should read naturally inside the v3 body, not feel like pasted-in blocks from HEAD. The v3 rewrite changed the surrounding context in some places (e.g., the topology description in dev-orchestrator.md changed from "spawns design-orchestrator, planner, and impl-orchestrator" to "spawns design-orchestrator and impl-orchestrator with planning impl-orch owning the planner spawn"). When restoring standing principles:

- Place them where they fit the v3 body structure, not necessarily in the same section heading they had in HEAD.
- Adapt the framing phrasing if the standing principle references v2 concepts that v3 replaced (e.g., references to `scenarios/` in HEAD should be dropped or updated to `spec leaves` when restoring).
- Keep the *reasoning* that made the standing principle load-bearing. Dropping the why reduces the principle to a brittle rule.
- The restoration is not a revert — it is a surgical re-addition of specific content into a file that has moved forward in other ways.

## Quality bar

After the restoration:

- Every affected orchestrator body carries its orchestrator-coordinates-not-implements principle with the altitude reasoning intact.
- Every affected orchestrator body carries the meridian-spawn-over-Agent-tool boilerplate with the spawns-persist-reports reasoning.
- `impl-orchestrator.md` carries the concurrent-work-tree safety guidance.
- `dev-orchestrator.md` carries the user-confirmation gate, the "How You Engage" craft, and the "Match Process to Problem" scaling anchors.
- `skills/planning/SKILL.md` carries the thoroughness, staffing, and phase-decomposition sections.
- None of the v3-direction-change residues from the "leave removed" list reappear.
- `git -C meridian-dev-workflow diff --check` is clean.

## Return

Terminal report listing:
- Files touched with a summary of what was restored per file
- Any judgment calls where you chose not to restore something from HEAD because it was v3-outdated or because the v3 rewrite covered it differently
- Any HEAD content you noticed worth restoring that isn't in my list above — flag for user review
- Any "leave removed" items you noticed reappearing in HEAD that I didn't name explicitly — flag for user review

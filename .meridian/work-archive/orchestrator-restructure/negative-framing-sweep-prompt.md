# Sweep negative framings from v3 rewrite: omission over prohibition

The p1559 rewrite of `meridian-dev-workflow/` is mostly clean but carries residual belt-and-suspenders prohibitions for things v3 already describes positively elsewhere — e.g. "never spawn `@planner` directly" when the delegation chain already routes through planning impl-orch. Remove the prohibition sentences where omission is enough.

## The principle

Positive descriptions are the specification. Adding "do not X" on top of a positive spec plants X in the mental model as a loophole to resist. Modern Claude models over-comply on negative phrasings and literally construct scenarios to apply them, so the prohibition does the opposite of what the author intended — it invites the thing it's trying to prevent.

Omission is stronger than prohibition. If the positive delegation chain, behavior, or contract is described, delete the "do not" sentence. The absent behavior simply does not exist in the agent's mental model.

## Scope — files modified by p1559 that carry residual prohibitions

Focus on these files; the grep-known hits are listed so you can start there, but you should scan the full body of each file for other instances the grep missed.

**Agents:**
- `meridian-dev-workflow/agents/dev-orchestrator.md` — known hits around "never spawn `@planner`", "Do not resume planning impl-orch", "Do not patch design files inline"
- `meridian-dev-workflow/agents/design-orchestrator.md` — known hit on "Do not create or reference `scenarios/`"
- `meridian-dev-workflow/agents/impl-orchestrator.md` — known hits on "Never mix both roles", "Do not re-run probes", "Do not proceed to execution in the same spawn", "Do not use `scenarios/`", "not a separate gate"
- `meridian-dev-workflow/agents/planner.md` — known hit on "Do not invent new refactor entries"
- `meridian-dev-workflow/agents/coder.md`, `reviewer.md`, `smoke-tester.md`, `unit-tester.md`, `verifier.md` — scan for similar patterns

**Skills:**
- `meridian-dev-workflow/skills/dev-artifacts/SKILL.md` — known hit on "`scenarios/` is retired and must not be produced or consumed"
- `meridian-dev-workflow/skills/planning/SKILL.md` — known hit on "Do not invent new refactor entries"
- `meridian-dev-workflow/skills/ears-parsing/SKILL.md` — known hit on "Do not invent semantics to force a pass/fail"
- `meridian-dev-workflow/skills/verification/SKILL.md` — known hit on "Do not invent alternate acceptance contracts"
- `meridian-dev-workflow/skills/smoke-test/SKILL.md`, `unit-test/SKILL.md`, `dev-principles/SKILL.md` — scan for v3-specific prohibitions (leaving pre-existing standing principles alone per "what to leave alone" below)

## Things v3 decided to remove or restructure

Prohibitions of these are candidates for dropping:

- **Scenarios convention** — retired entirely. Don't mention `scenarios/`, don't prohibit it, just don't reference it at all.
- **`dev-principles` as a gate** — shared operating guidance loaded by relevant agents. Drop "not a gate" clauses; the positive "loaded as shared guidance" is sufficient.
- **Dev-orch spawning `@planner` directly** — planning impl-orch is the planner caller. Drop "never spawn `@planner` directly" — the positive delegation chain handles it.
- **Suspended-spawn across plan review** — terminated-spawn contract. Drop "do not resume" prohibitions; the positive "fresh execution impl-orch spawn" is sufficient.
- **Mixing planning and execution roles in one spawn** — each spawn is single-role. Drop "never mix" prohibitions if the positive role framing is already there.
- **Re-running probes already in feasibility.md** — consume as input. Drop "do not re-run" if the positive "read feasibility.md as input" is already there.
- **Planner inventing refactors** — sequence the agenda design identified. Drop "do not invent" if the positive "sequence what design produced" is there.
- **Scenario-era verification contracts** — spec leaves are the acceptance surface. Drop "do not use" prohibitions; the positive "verify against spec leaves" is sufficient.
- **Inventing semantics to force EARS pass/fail** — report unparseable instead. Drop "do not invent" if the positive escape-valve language is there.

## What to leave alone

Pre-existing standing principles that predate v3 and aren't direction changes we decided to remove. These are genuine behavioral constraints, not over-eager prohibitions:

- **`skills/dev-principles/SKILL.md`** content about refactor discipline, abstraction rules, deletion courage, Chesterton's fence — load-bearing engineering guidance. Some bullets use negative form and that's fine because the negative IS the constraint (e.g., "do not abstract yet at two similar cases"). Judgment call per bullet.
- **`agents/*.md` "never use built-in Agent tools" / "use `meridian spawn` for delegation"** — standing meridian boilerplate about the spawn-vs-Agent boundary. Not v3 scope.
- **`agents/*-orchestrator.md` "you don't edit source files" / "delegate with `meridian spawn`"** — standing orchestrator principle about coordination vs implementation. Pre-existing, not a v3 direction change. Judgment call on whether to rephrase positively ("Delegate with meridian spawn so work stays traceable on disk" alone is the positive form and could drop the "do not edit" clause) — if it reads cleaner without the prohibition, apply the same omission principle; if the prohibition earns its place as a standing orchestrator boundary, leave it.
- **Pre-existing content in agents that p1559 did not modify** — `investigator.md`, `tech-writer.md`, `architect.md`, `docs-orchestrator.md`, etc. Out of scope.

## Quality bar

After the sweep:
- Every agent body reads as a positive specification of what the agent does, with the invalid paths simply absent rather than listed and rejected.
- Every standing principle that genuinely earns its negative form (judgment pattern you apply per instance) stays intact.
- `git diff --check` clean.
- A grep for "never", "do not", "must not", "shall not", "cannot" turns up only standing principles from the "what to leave alone" set.

## Return

Terminal report listing:
- Files touched with a one-line change summary each (what was removed, what was rephrased)
- Any instances you decided to leave in place with reasoning (judgment calls that went the other way)
- Any prohibitions you weren't sure about and want flagged for review

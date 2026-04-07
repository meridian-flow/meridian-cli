# Dev-Workflow Moves: Session Mining

## Why Move This At All

`__meridian-session-context` in base does two unrelated jobs:

1. **CLI reference** for `meridian session log/search` and `meridian work sessions`.
2. **Workflow guidance** for *how a dev-workflow agent uses those commands* — parent-session inheritance to recover the launching conversation, delegating bulk transcript reading to `@explorer` instead of doing it inline, and discovering all sessions tied to a single work item before mining.

Job 1 belongs in `__meridian-cli` (every other CLI surface lives there). Job 2 cannot live in base because it prescribes a concrete dev-workflow agent (`@explorer`) — that's the cross-layer leak the user explicitly wants closed.

The fix is to move Job 2 into a new dev-workflow skill that *assumes* `__meridian-cli` is loaded and adds the workflow patterns on top.

## New Skill: `session-mining` (working name)

### Frontmatter

```yaml
---
name: session-mining
description: "Workflow patterns for mining conversation history during dev work — recovering decisions from parent sessions, delegating bulk transcript reading, and discovering all sessions tied to a work item. Assumes the meridian session CLI is already understood (see __meridian-cli)."
---
```

### Body Outline (target ≤ 80 lines)

**Why mining matters.** One paragraph: design decisions, rejected alternatives, and constraint discoveries live in conversation, not in code or docs. They evaporate at compaction. The cheapest moment to recover them is right before the next agent starts work.

**Recover from the parent session first.** Two short paragraphs: explain the inheritance mechanic (`$MERIDIAN_CHAT_ID` is the launching session, not the spawn's own), and why it's the highest-leverage starting point — most decisions an agent needs to honor were made in the conversation that spawned it. One example command line.

**Delegate bulk reading, don't inline it.** When the question is "what was decided across this whole work item's history," spawn an explorer with `__meridian-cli` loaded and have it return a synthesis. Reading 200 messages inline burns context that the synthesizing agent needs for its actual work. One example spawn command. The spawned explorer needs `__meridian-cli` (for the session commands) but does **not** need `session-mining` itself, because the explorer is doing the reading, not orchestrating further delegation. Note: if you *are* an explorer, mine directly instead of recursing.

**Discover sessions per work item.** When the work item has been touched by multiple sessions over time (interrupted runs, reopens, multi-day work), use `meridian work sessions` to enumerate them before mining. Otherwise you only see the current session's history and miss prior decisions.

**When to skip mining entirely.** If the spawning prompt already includes the relevant context, or the work item has fresh design docs that capture the decisions, mining is wasted effort. Skim the artifacts first; mine only the gaps.

### Style Constraints

- Frame as workflow guidance, not CLI reference. Every command example is short and serves to illustrate a pattern, not teach the flag.
- Cross-references to base skills are fine — this skill is allowed to assume `__meridian-cli` because it lives one layer above.
- May reference dev-workflow agents by name (`@explorer`) — that's the entire point of moving it here.

## Consumer Profile Updates

See `06-consumer-profile-updates.md` for the full diff. Summary of what changes in dev-workflow:

| Profile | Today | After |
|---|---|---|
| `dev-orchestrator` | `__meridian-session-context` in skills array; no body refs | Replace with `session-mining`; add `__meridian-cli` if the profile expected the CLI half |
| `docs-orchestrator` | `__meridian-session-context` in skills array; body line 44 references `/__meridian-session-context` | Replace skill; update body to reference `/session-mining` (workflow) and rely on `__meridian-cli` for the CLI half |
| `code-documenter` | `__meridian-session-context` in skills array; body line 74 references `/__meridian-session-context` | Same treatment as `docs-orchestrator` |

`__meridian-cli` should be loaded explicitly into any profile that previously got it transitively through `__meridian-session-context`. The planner enumerates which profiles need it; the dev-orchestrator/docs-orchestrator/code-documenter trio is the certain set, and a sweep over both submodules should confirm there are no others.

## Naming: Locked as `session-mining`

After review, the working name `session-mining` is locked as the final name. Half-deferring naming creates a real coordination risk — different files would have ended up with different names — and the alternatives in the decision log don't beat it. The new SKILL file, all consumer profile skills arrays, and every body-text reference use `session-mining` consistently. The planner does not need to revisit this.

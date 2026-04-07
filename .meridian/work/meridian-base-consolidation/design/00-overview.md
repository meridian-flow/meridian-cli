# meridian-base Skills Consolidation — Overview

## Goal

Collapse meridian-base's CLI-reference skills into a single principle-teaching skill that points at `meridian --help` / `mars --help` as the canonical reference, fix the cross-layer leaks that let dev-workflow agent names (`@explorer`, `@reviewer`, `@dev-orchestrator`) appear in base, and rebalance ownership of session-mining workflow patterns into meridian-dev-workflow where they belong.

This is the structural execution of GitHub issue #8, refined by the prior dev-conversation decisions captured in the spawning prompt.

## Target State at a Glance

**meridian-base/skills/** ends with five `__meridian-*` skills, each earning its context cost:

| Skill | Status | Owns |
|---|---|---|
| `__meridian-spawn` | unchanged | Delegation, model selection, fan-out, context handoff mechanics |
| `__meridian-work-coordination` | unchanged | Work lifecycle and artifact placement principles |
| `__meridian-privilege-escalation` | unchanged | Permission escalation flow |
| `__meridian-cli` | **NEW** | Mental model of meridian, where to learn each surface (`--help`), principles `--help` can't teach. Replaces `__mars`, `__meridian-diagnostics`, and the *CLI reference* parts of `__meridian-session-context`. |
| `agent-creator`, `skill-creator` | unchanged | Authoring guides |

**Removed from meridian-base/skills/**:

- `__mars/` — folded into `__meridian-cli`
- `__meridian-diagnostics/` — folded into `__meridian-cli`
- `__meridian-session-context/` — split: CLI bits fold into `__meridian-cli`, workflow patterns move to dev-workflow

**meridian-dev-workflow/skills/** gains one new skill:

- `session-mining` (working name — see `decisions.md`) — workflow patterns for parent-session inheritance, delegating bulk transcript reading to `@explorer`, and discovering sessions per work item. Layered above `__meridian-cli`, which it assumes is loaded.

## Why This Shape

The four-skill table in issue #8 is the right destination, but the user added one structural refinement: rather than keeping a thin `__meridian-session-context` in base whose two real responsibilities are *(a) the CLI reference for `meridian session ...` / `meridian work sessions`* and *(b) the workflow advice "delegate to @explorer"*, we split it. Both halves become more honest:

- The CLI reference half belongs alongside every other CLI reference, in `__meridian-cli` — so an agent that already knows how to read `meridian --help` doesn't need a second skill to learn it again for one subcommand group.
- The workflow half is dev-workflow's responsibility because it prescribes concrete dev-workflow agent roles. It cannot live in base without leaking layering.

`__meridian-cli` is named explicitly (not `__meridian`) so the description is unambiguous: "the CLI surface, how to learn it, principles behind it" — a separate concept from any future `__meridian` skill that might teach the project's broader runtime model.

## Documents in This Design

| Doc | Topic |
|---|---|
| `01-target-skill-set.md` | What stays, what dies, what's new — the full disposition table |
| `02-meridian-cli-skill.md` | Body outline and structure for the new `__meridian-cli` skill |
| `03-dev-workflow-moves.md` | The new dev-workflow session-mining skill and how dev-workflow profiles consume it |
| `04-cli-help-gaps.md` | `--help` text gaps and proposed additions (the prerequisite from issue #8) |
| `05-cross-layer-leaks.md` | Example-vs-generic policy and the full fix list for `@dev-workflow-agent` references in base |
| `06-consumer-profile-updates.md` | Agent profile skill-array and body updates across both submodules |
| `decisions.md` | Tradeoffs and rejected alternatives (in work root, not under design/) |

## Read Order

Read `00-overview.md` first, then jump to whichever piece you're touching. `01-target-skill-set.md` is the spine — it links everywhere else. `04` and `05` are independent and can be reviewed in parallel by different reviewers.

## What This Design Does NOT Cover

- No changes to `__meridian-work-coordination` content.
- `__meridian-spawn` gets three small surgical changes only: (a) dangling-ref fix, (b) the four principle-restatement trims per D9, (c) the pre-existing `mars models -h` bug fix at line 57. No other content changes.
- No changes to dev-workflow's review/coding/planning skills.
- No changes to harness adapters, mars internals, or meridian's runtime — this is primarily a documentation/skill-layering refactor. The only source-tree edits are `--help` docstring expansions in `src/meridian/cli/` and possibly mars (Gaps 8 and 9 in `04`).
- No new meridian or mars commands — only `--help` text additions, with the open question of whether mars grows a `mars init --schema` flag for the TOML reference (Gap 8 option 1). If a gap is large enough to need a new flag, the planner decides whether to bundle it or defer to a separate work item.

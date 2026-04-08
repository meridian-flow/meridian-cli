# Target Skill Set

The disposition of every meridian-base skill, every cross-layer-relevant dev-workflow skill, and every consumer that needs to follow.

## meridian-base/skills/

| Skill | Action | Notes |
|---|---|---|
| `__meridian-spawn` | **Keep, with body trims.** Remove the line pointing at `__meridian-session-context`. Trim the duplicated CLI principles (JSON discipline, auto-recovery, env vars) to cross-references — `__meridian-cli` becomes canonical (see D9). Fix the pre-existing bug at line 57 (`mars models -h` → `models -h`). | Already principles-first; the trims are about removing duplication with the new skill, not re-scoping. |
| `__meridian-work-coordination` | **Keep.** No body changes. | Already principles-first. |
| `__meridian-privilege-escalation` | **Keep.** No body changes. | Niche, dormant skill. |
| `__meridian-cli` | **Create.** See `02-meridian-cli-skill.md` for body outline. | New singular CLI reference skill. |
| `__mars` | **Delete.** Content folded into `__meridian-cli` as the "Mars" section. | The current body is ~80% a command table that duplicates `mars --help`. |
| `__meridian-diagnostics` | **Delete.** Content folded into `__meridian-cli` as the "Diagnostics" section. | The "Common Failure Patterns" table is the only durable content; everything else duplicates `meridian doctor` / `meridian spawn show` output. |
| `__meridian-session-context` | **Delete from base.** Split: CLI bits → `__meridian-cli` "Sessions" section; workflow bits → new dev-workflow skill (see `03`). | Removes the `@explorer` cross-layer leak. |
| `agent-creator` | **Keep, with example-policy fixes.** See `05-cross-layer-leaks.md`. | Generic-guidance refs to dev-workflow agents are corrected; pure example refs stay. |
| `skill-creator` | **Keep, with example-policy fixes.** See `05-cross-layer-leaks.md`. | Same treatment. |

## meridian-base/agents/

| Agent | Action | Notes |
|---|---|---|
| `__meridian-orchestrator` | Body fix only — line 29 references `@reviewers` (a dev-workflow agent) as generic guidance. Rephrase to model-agnostic ("fan out additional reviewing spawns"). Skills array unchanged. | See `05-cross-layer-leaks.md`. |
| `__meridian-subagent` | No change. | Skills array is empty. |

## meridian-dev-workflow/skills/

| Skill | Action | Notes |
|---|---|---|
| `session-mining` | **Create.** See `03-dev-workflow-moves.md` for body outline. Name is locked (D3 revised). | Replaces the workflow half of `__meridian-session-context`. Assumes `__meridian-cli` is loaded and does not redocument session CLI commands. |
| All other dev-workflow skills | No change. | |

## meridian-dev-workflow/agents/

Skills-array updates to remove `__meridian-session-context` and add the new dev-workflow session-mining skill where appropriate. Body-text updates to replace `/__meridian-session-context` mentions. See `06-consumer-profile-updates.md` for the full list.

## Net Change

- meridian-base: 8 skills → 6 skills (–25%), no skill duplicates `--help` content.
- meridian-dev-workflow: +1 skill that owns one bounded workflow concept.
- One cross-layer leak class eliminated (`@explorer` in base).
- Generic-guidance leaks in `agent-creator` / `skill-creator` / `__meridian-orchestrator` corrected; pure example refs preserved per the policy in `05-cross-layer-leaks.md`.

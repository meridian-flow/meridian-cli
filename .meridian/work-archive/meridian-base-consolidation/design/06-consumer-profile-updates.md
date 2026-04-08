# Consumer Profile Updates

Every agent profile that lists a deleted skill in its `skills:` array, and every body-text reference to one of those skills, must be updated. This doc enumerates the exact set found in both submodules.

## Search Methodology

Looking for any non-`.agents/` reference to:

- `__mars`
- `__meridian-diagnostics`
- `__meridian-session-context`

across `meridian-base/` and `meridian-dev-workflow/` (the source submodules).

## Findings

### `__mars` references

**None.** No agent profile in either submodule lists `__mars` in its skills array. The skill is loaded ad-hoc by orchestrators as needed. Only README mentions exist:

- `meridian-base/README.md:48` — table entry. Update to remove the row (or replace with `__meridian-cli`).

### `__meridian-diagnostics` references

**None.** No profile lists it. README mention only:

- `meridian-base/README.md:49` — table entry. Update to remove the row.

### `__meridian-session-context` references

| File | Line | What | Fix |
|---|---|---|---|
| `meridian-base/README.md` | 47 | Table entry | Remove row (skill is being deleted from base) |
| `meridian-dev-workflow/README.md` | 118 | Bullet "(base)" reference | Replace with `session-mining` (dev-workflow) and `__meridian-cli` (base, if relevant) |
| `meridian-dev-workflow/agents/code-documenter.md` | 10 | `skills: [..., __meridian-session-context, decision-log]` | Replace `__meridian-session-context` with `session-mining`. Add `__meridian-cli` if the profile depends on the CLI half. |
| `meridian-dev-workflow/agents/code-documenter.md` | 74 | Body text: `Use /__meridian-session-context to search and navigate transcripts` | Rewrite to point at `/session-mining` for the workflow pattern; let the CLI half come from `__meridian-cli`. |
| `meridian-dev-workflow/agents/dev-orchestrator.md` | 10 | `skills: [..., __meridian-session-context, ...]` | Same skill swap. Add `__meridian-cli` explicitly. |
| `meridian-dev-workflow/agents/docs-orchestrator.md` | 12 | `skills: [..., __meridian-session-context, ...]` | Same skill swap. Add `__meridian-cli` explicitly. |
| `meridian-dev-workflow/agents/docs-orchestrator.md` | 44 | Body: `Use /__meridian-session-context to search transcripts...` | Rewrite to `/session-mining`. |

### Other base agents

- `meridian-base/agents/__meridian-orchestrator.md` (line 29): the `@reviewers` generic-guidance leak (see `05-cross-layer-leaks.md`). Skills array is unaffected.
- `meridian-base/agents/__meridian-subagent.md`: empty skills array, unchanged.

## `__meridian-cli` Adoption

The new skill is added to every profile whose body invokes a meridian or mars CLI command beyond `meridian spawn` and `meridian work` (which `__meridian-spawn` and `__meridian-work-coordination` already cover canonically).

**Rule, in priority order:**

1. **Always add** if the profile body mentions any of: `meridian session`, `meridian config`, `meridian doctor`, `meridian models`, `meridian mars`, `mars`, spawn-failure diagnosis, status-string interpretation, environment variables, or `.meridian/spawns/<id>/` artifact layout.
2. **Always add** if the profile previously listed `__mars`, `__meridian-diagnostics`, or `__meridian-session-context` in its skills array (it depended transitively on the CLI reference content of those).
3. **Skip** if the profile is the base orchestrator (`__meridian-orchestrator`) or base subagent (`__meridian-subagent`) — both stay minimal and load CLI skills ad-hoc.

Applying the rule to the agents in `meridian-dev-workflow/agents/`:

| Profile | Add `__meridian-cli`? | Why |
|---|---|---|
| `dev-orchestrator` | **Yes** | Rule 1 + 2 — diagnoses spawns, mines sessions, runs `meridian config`-style introspection |
| `docs-orchestrator` | **Yes** | Rule 1 + 2 — mines sessions, manages work artifacts |
| `code-documenter` | **Yes** | Rule 1 + 2 — reads reports and session logs |
| `impl-orchestrator` | **Yes** (verify) | Likely diagnoses failures during impl phases — verify by reading body |
| `design-orchestrator` | **Yes** (verify) | Same |
| `planner` / `architect` / `reviewer` / `coder` / `refactor-reviewer` / `verifier` / `tester` (smoke/browser/unit) / `explorer` / `investigator` / `tech-writer` | **Sweep per body — apply Rule 1** | Each profile gets a one-grep check for the keywords in Rule 1. The implementer enumerates the result; the planner does not need to pre-decide. |
| `__meridian-orchestrator` (base) | **No** | Rule 3 |
| `__meridian-subagent` (base) | **No** | Rule 3 |

**Verification step in the implementation phase:** after applying the rule, grep every dev-workflow agent body for `meridian session`, `meridian config`, `meridian doctor`, `meridian mars`, `\.meridian/spawns`, `MERIDIAN_`, and confirm every match lives in a profile that has `__meridian-cli` in its skills array. Any mismatch is either a missed addition (fix) or a body-text reference that should be removed (also fix).

## README Updates

Both `meridian-base/README.md` and `meridian-dev-workflow/README.md` have skill tables that enumerate what each package ships. After consolidation:

- meridian-base README: remove `__mars`, `__meridian-diagnostics`, `__meridian-session-context` rows. Add `__meridian-cli` row.
- meridian-dev-workflow README: remove the line referencing `__meridian-session-context (base)`. Add a line for the new `session-mining` skill.

## Verification

After all profile updates, the project itself runs `meridian mars sync` and verifies:

1. No profile in either submodule references a deleted skill.
2. Every profile that adds `__meridian-cli` actually loads it (check `.agents/` after sync).
3. `meridian mars doctor` reports clean.
4. A smoke test: `meridian spawn -a dev-orchestrator --dry-run -p "test"` resolves the profile without error.

The planner should bundle this verification into the final phase.

# Harness Adapters

Meridian routes spawns to harness adapters instead of calling model APIs directly in normal CLI flow.

## Routing

Model -> harness routing:

| Pattern | Harness |
|---|---|
| `claude-*`, `opus*`, `sonnet*`, `haiku*` | Claude |
| `gpt-*`, `o1*`, `o3*`, `o4*`, `codex*` | Codex |
| `opencode-*`, `gemini*`, contains `/` | OpenCode |
| unknown | Codex fallback + warning |

## Adapters and Capabilities

| Adapter | Stream events | Resume | Fork | Native skills | Native agents |
|---|---:|---:|---:|---:|---:|
| Claude | yes | yes | yes | yes | yes |
| Codex | yes | yes | no | yes | no |
| OpenCode | yes | yes | yes | yes | no |
| Direct (API) | no | no | no | no | no |

## Command Shapes

### Claude

- Base: `claude -p <prompt> --model <model> ...`
- Resume: `--resume <harness_session_id>`
- Fork: `--fork-session`
- Native agent passthrough: `--agent <name>`
- Ad-hoc agent+skills payload (when needed): `--agents <json>`

### Codex

- Base: `codex exec --json ...`
- Resume: `codex exec --json resume <harness_session_id> ...`

### OpenCode

- Base: `opencode run ...`
- Resume: `--session <harness_session_id>`
- Fork: `--fork`
- `opencode-` prefix is stripped before passing model value.

## Sandbox Mapping

Meridian translates agent profile `sandbox:` values to harness-specific
sandbox flags at launch time.

`meridian spawn` does not expose a `--permission` flag. The sandbox tier comes
from the selected agent profile `sandbox:` value.

### Tier Mapping

| Tier | Claude | Codex |
|---|---|---|
| `read-only` | `--allowedTools Read,Glob,Grep,Bash(git status),...` | `--sandbox read-only` |
| `workspace-write` | adds `Edit,Write,Bash(git add),Bash(git commit)` | `--sandbox workspace-write` |
| `full-access` | adds `WebFetch,WebSearch,Bash` | `--sandbox danger-full-access` |

Agent profile `sandbox` values map into those tiers:

- `read-only` -> `read-only`
- `workspace-write` -> `workspace-write`
- `full-access` -> `full-access`
- `danger-full-access` -> `full-access`
- `unrestricted` -> `full-access`

Use `--` passthrough when you need harness-specific flags in addition to the
profile-derived tier, for example:

- `meridian spawn -m claude-opus-4-6 -p "test" -- --sandbox workspace-write`

### Yolo Mode

`--yolo` maps to harness-specific bypass flags:

- Claude: `--dangerously-skip-permissions`
- Codex: `--dangerously-bypass-approvals-and-sandbox`

Note that for these harnesses, `--yolo` bypasses both approval prompts and
sandbox restrictions — the two are not independent in practice.

### Explicit Tool Allowlists

If an agent profile defines `allowed_tools`, Meridian may use that explicit
allowlist instead of the tier-derived mapping.

## Runtime Controls

The small amount of Meridian-owned execution control that exists today mostly
shows up at harness launch boundaries.

### Depth Limiting

Nested spawn depth is enforced by Meridian before launching another harness
process.

```text
MERIDIAN_DEPTH=0 -> meridian spawn (child depth 1)
  -> MERIDIAN_DEPTH=1 -> meridian spawn (child depth 2)
  -> MERIDIAN_DEPTH=2 -> meridian spawn (child depth 3)
  -> MERIDIAN_DEPTH=3 -> refused by Meridian by default
```

`MERIDIAN_MAX_DEPTH` controls the ceiling. Default: `3`.

### Environment Propagation

Spawned harness processes inherit Meridian runtime context such as:

- `MERIDIAN_FS_DIR`
- `MERIDIAN_SPAWN_ID`
- `MERIDIAN_PARENT_SPAWN_ID`
- `MERIDIAN_DEPTH`
- `MERIDIAN_REPO_ROOT`
- `MERIDIAN_STATE_ROOT`

Trusted harness launches broadly inherit the parent environment in addition to
that Meridian context. Meridian does not provide a general secret-isolation
layer for normal harness execution.

### Budget, Guardrail, And Secret Hooks

Meridian contains runner-level support for:

- budget enforcement
- post-run guardrail scripts
- redaction of injected `MERIDIAN_SECRET_<KEY>` values

Those are currently runner hooks, not normal `meridian spawn` user features:

- `meridian spawn` does not expose budget, guardrail, or secret flags
- the standard spawn execution path does not currently wire those values into
  the runner
- treat them as integration hooks unless and until they are surfaced through
  the main CLI flow

## Primary Agent Launch

Bare `meridian` launches a primary harness session. `meridian --continue` resumes from prior session context when supported.

If the selected primary profile is an on-disk user profile, Meridian uses Claude native profile passthrough:

- `claude --agent <profile> --append-system-prompt <primary prompt> --model <model>`

Otherwise Meridian composes the prompt and passes it via `--system-prompt`.

Fresh and forked primary launches now also inject an installed agent catalog:

- Claude: agent inventory is included in the `--append-system-prompt` payload
- Codex: agent inventory is flattened into the inline primary prompt
- OpenCode: agent inventory is flattened into the inline primary prompt

This startup inventory is additive. It does not replace the harness-specific
loading/injection path for the selected agent profile body or its skills.

Resume launches keep the existing behavior and do not receive a newly composed startup inventory block.

## Session Continuation Fields

For spawn continuation (`meridian spawn --continue SPAWN_ID` with optional `--fork`), Meridian resolves and passes harness session context as:

- `continue_harness_session_id`
- `continue_fork`

## OpenCode Compaction Plugin

**Not yet implemented.** The compaction reinjection plugin (`.opencode/plugins/meridian.ts`) is planned but does not exist in the repo. No loader path or plugin file has been added.

Intended behavior: on `experimental.session.compacting`, read `.meridian/sessions.jsonl`, find the matching session, and re-inject agent profile and skill content. See `backlog/plan-cleanup-notes.md` (Harness capability follow-up) for the open tracking item.

## Direct Adapter

A `DirectAdapter` (Anthropic Messages API tool-calling) exists in the harness registry for programmatic use, but standard spawn routing (`meridian spawn`) uses CLI harnesses (`claude`, `codex`, `opencode`).

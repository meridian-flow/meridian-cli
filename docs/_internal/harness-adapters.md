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

## Permissions And Approval

Meridian owns a small cross-harness permission model and translates it to
harness-specific controls at launch time.

`meridian spawn` does not expose a `--permission` flag. The spawn tier comes
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

### Approval Semantics

`meridian spawn` supports:

- default approval mode `confirm`
- `--yolo` as shorthand for `approval=auto`

Important caveat: approval behavior is harness-defined after Meridian translates
it. For Claude and Codex, `--approval auto` maps to the harness bypass flags
rather than a separate Meridian-controlled approval channel:

- Claude: `--dangerously-skip-permissions`
- Codex: `--dangerously-bypass-approvals-and-sandbox`

So for those harnesses, approval and sandboxing are not fully independent in
practice.

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

## Session Continuation Fields

For spawn continuation (`meridian spawn --continue SPAWN_ID` with optional `--fork`), Meridian resolves and passes harness session context as:

- `continue_harness_session_id`
- `continue_fork`

## OpenCode Compaction Plugin

OpenCode compaction reinjection lives at:

- `.opencode/plugins/meridian.ts`

On `experimental.session.compacting`, it reads `.meridian/sessions.jsonl`, finds the matching session, and re-injects agent profile and skill content.

## Direct Adapter

A `DirectAdapter` (Anthropic Messages API tool-calling) exists in the harness registry for programmatic use, but standard spawn routing (`meridian spawn`) uses CLI harnesses (`claude`, `codex`, `opencode`).

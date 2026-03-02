# Harness Adapters

Meridian routes spawns to harness adapters instead of calling model APIs directly in normal CLI flow.

Developer note:
- Canonical domain term is `spawn` (see [Developer Terminology](developer-terminology.md)).
- This document uses some current `run` wording where it mirrors present code/CLI names.

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

- Base: `codex exec ...`
- Resume: `codex exec resume <harness_session_id> ...`

### OpenCode

- Base: `opencode run ...`
- Resume: `--session <harness_session_id>`
- Fork: `--fork`
- `opencode-` prefix is stripped before passing model value.

## Primary Agent Launch (Space)

`meridian space start/resume` and `meridian start` launch a primary Claude harness session.

If the selected primary profile is an on-disk user profile, Meridian uses Claude native profile passthrough:

- `claude --agent <profile> --append-system-prompt <space prompt> --model <model>`

Otherwise Meridian composes the prompt and passes it via `--system-prompt`.

## Session Continuation Fields

For spawn continuation (currently `run continue`), Meridian resolves and passes harness session context as:

- `continue_harness_session_id`
- `continue_fork`

## OpenCode Compaction Plugin

OpenCode compaction reinjection lives at:

- `.opencode/plugins/meridian.ts`

On `experimental.session.compacting`, it reads `.meridian/.spaces/<space-id>/sessions.jsonl`, finds the matching session, and re-injects agent profile and skill content.

## Direct Adapter

A `DirectAdapter` (Anthropic Messages API tool-calling) exists in the harness registry for programmatic use, but standard spawn routing (currently `meridian spawn spawn`) uses CLI harnesses (`claude`, `codex`, `opencode`).

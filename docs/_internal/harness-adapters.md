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
- `MERIDIAN_PROJECT_DIR`
- `MERIDIAN_RUNTIME_DIR`

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

### Content Channel Routing

Both primary and spawn launches classify composed content into three semantic categories before passing to the harness adapter via `project_content()`:

| Category | What's in it |
|---|---|
| `SYSTEM_INSTRUCTION` | Skills, agent profile body, report instruction, agent inventory, passthrough `--append-system-prompt` fragments |
| `USER_TASK_PROMPT` | User-supplied request text (`-p` / `--prompt-file`) |
| `TASK_CONTEXT` | Reference files (`-f`), prior-run output (`--from`) |

Each harness adapter decides how to route these categories to its native CLI channels:

| Category | Claude | Codex | OpenCode |
|---|---|---|---|
| `SYSTEM_INSTRUCTION` | `--append-system-prompt-file` | inline (top) | inline |
| `USER_TASK_PROMPT` | positional argument | inline (after system) | inline |
| `TASK_CONTEXT` | user-turn (prepended to prompt) | inline (after prompt) | native `--file` or inline |

For Claude native profile passthrough, Meridian uses:

```
claude --agent <profile> --append-system-prompt <inventory> --model <model>
```

For composed (non-native) launches, Meridian routes system content to `--append-system-prompt-file` and user task content as a positional argument.

Fresh and forked primary launches inject an installed agent catalog as `SYSTEM_INSTRUCTION`:

- Claude: agent inventory is included in the `--append-system-prompt-file` payload
- Codex: agent inventory is flattened into the inline primary prompt
- OpenCode: agent inventory is flattened into the inline primary prompt

This startup inventory is additive. It does not replace the harness-specific
loading/injection path for the selected agent profile body or its skills.

Resume launches keep the existing behavior and do not receive a newly composed startup inventory block.

### Observability Artifacts

After every launch (primary and spawn), Meridian writes artifacts to the spawn log directory (`.meridian/spawns/<id>/`) that expose how content was routed. The same `write_projection_artifacts()` path is shared; the `surface` field distinguishes primary vs. spawn in the manifest.

| Artifact | Content | Written when |
|---|---|---|
| `system-prompt.md` | `SYSTEM_INSTRUCTION` content as sent to the system-prompt channel | System-prompt content exists (Claude composed launches) |
| `starting-prompt.md` | Full user-turn content (`USER_TASK_PROMPT` + prepended `TASK_CONTEXT`) | User-turn content exists |
| `references.json` | Per-reference routing decisions (inline / native-injection / omitted) | References exist |
| `projection-manifest.json` | Harness ID, surface, and per-category channel routing decisions | Every launch |

`references.json` is adapter-owned: OpenCode decides per reference whether to pass `--file` (native-injection) or inline the body. Claude and Codex mark all references as inline.

`projection-manifest.json` schema:

```json
{
  "harness": "claude" | "codex" | "opencode",
  "surface": "primary" | "spawn",
  "channels": {
    "system_instruction": "append-system-prompt" | "inline" | "none",
    "user_task_prompt": "user-turn" | "inline",
    "task_context": "user-turn" | "inline" | "native-injection"
  }
}
```

`prompt.md` (the legacy spawn artifact) is no longer written. Any existing `prompt.md` files are deleted when the spawn executes.

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

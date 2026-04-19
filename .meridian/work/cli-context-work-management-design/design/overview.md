# Work Context Query Model

## Problem

Agents cannot reliably access their work context. The current model injects `MERIDIAN_WORK_DIR`, `MERIDIAN_FS_DIR`, and `MERIDIAN_WORK_ID` as env vars at spawn launch time, but:

1. **Shell statelessness** — each Bash tool call is a fresh process; env vars don't persist between calls
2. **Primary harness blindness** — the harness that runs `work switch` doesn't see the env vars (they're only projected into children)
3. **Confusing mental model** — agents assume `$MERIDIAN_WORK_DIR` is "just there" when it's actually derived from session state at launch time
4. **Prompt/skill misguidance** — current docs teach a broken pattern (`$MERIDIAN_WORK_DIR` references that often fail)

## Decision

**Kill env var projection. Make agents query for work context explicitly.**

## New Command: `meridian work current`

Returns the current work id, resolved from session attachment.

### Output Format

| Condition | Format |
|-----------|--------|
| `--json` flag | JSON |
| `MERIDIAN_DEPTH > 0` (inside spawn) | JSON |
| Otherwise (human at terminal) | Text |

### Human Output (default)

```
cli-context-work-management-design
```

No work attached:
```
(none)
```

### JSON Output (agents / `--json`)

```json
{"work_id": "cli-context-work-management-design"}
```

No work attached:
```json
{"work_id": null}
```

### Path Derivation

Agents derive paths from conventions:

| Path | Convention |
|------|------------|
| Work dir | `.meridian/work/{work_id}/` |
| FS dir | `.meridian/fs/` |
| State root | `.meridian/` |

All paths relative to repo root. No absolute paths returned.

## Env Vars Killed

| Var | Replacement |
|-----|-------------|
| `MERIDIAN_WORK_ID` | `meridian work current` |
| `MERIDIAN_WORK_DIR` | `.meridian/work/{work_id}/` |
| `MERIDIAN_FS_DIR` | `.meridian/fs/` |

## Env Vars Kept

| Var | Purpose |
|-----|---------|
| `MERIDIAN_CHAT_ID` | Session identity for lookups |
| `MERIDIAN_DEPTH` | Spawn nesting level, output format detection |
| `MERIDIAN_STATE_ROOT` | Optional override for `.meridian/` location |

## `work switch` Behavior

`work switch <id>` mutates session attachment (chat_id → work_id in session store).

Human output:
```
Switched to cli-context-work-management-design
```

JSON output (depth > 0 or `--json`):
```json
{"work_id": "cli-context-work-management-design", "switched": true}
```

## Agent Pattern

Before (broken):
```bash
cat "$MERIDIAN_WORK_DIR/design/overview.md"
```

After (explicit):
```bash
WORK_ID=$(meridian work current)
cat ".meridian/work/$WORK_ID/design/overview.md"
```

Or with JSON parsing when needed:
```bash
WORK_ID=$(meridian work current --json | jq -r .work_id)
```

## Spawn Inheritance

Spawns inherit session identity via `MERIDIAN_CHAT_ID`. The spawned agent calls `meridian work current` to get its work id — same resolution path as any agent.

## Migration

### Prompt/Skill Updates Required

1. Replace `$MERIDIAN_WORK_DIR` with query + convention pattern
2. Replace `$MERIDIAN_FS_DIR` with `.meridian/fs/`
3. Add "query your context" guidance
4. Remove "env vars are inherited" language

### Code Changes

1. Remove env var injection in `src/meridian/lib/launch/env.py`
2. Add `work current` subcommand
3. Update output format logic (depth > 0 → JSON)
4. Remove `MERIDIAN_WORK_*` from reserved env checks

## Tradeoffs

**Pros:**
- Explicit over implicit
- Works everywhere
- Minimal output (just work_id)
- Human-friendly by default

**Cons:**
- Breaking change to prompts/skills
- Extra CLI call for agents

## Research References

- p2187: Local meridian work/context ergonomics
- p2188: AI CLI context patterns
- p2191: Prompt/work contract audit

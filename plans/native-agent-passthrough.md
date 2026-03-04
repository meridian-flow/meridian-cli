# Native Agent Passthrough for Claude Harness

**Status:** completed (2026-03-04)

## Implementation Snapshot

- Claude harness supports native agents (`supports_native_agents=True`) and uses `--agent`.
- Spawn flow uses native-agent passthrough path in `_spawn_prepare.py` for Claude.
- Claude adapter supports ad-hoc agent JSON via `--agents`.
- `launch.py` primary flow uses `--agent` + `--append-system-prompt`.
- Key commits: `e444f60`, `9f39e24`, `905df58`, `77cffef`, `a28143b`.

## Problem

Meridian currently reads agent profiles and skill content itself, then injects everything into a composed prompt string. This means:

1. **Skills don't survive context compaction** — Claude's native agent loading keeps skills persistent across compaction; our injection doesn't
2. **Meridian duplicates work** the harness already does — Claude discovers agents from `.claude/agents/`, `.agents/agents/` natively
3. **Agent profiles designed for Claude** (with `allowedTools`, `model`, `permissionMode`, etc.) lose those fields when we only extract the body text

## Design

### Claude harness: native passthrough

**Case 1 — Named agent, no extra skills:**
```
meridian run spawn --agent coder -m claude-haiku-4-5 -p "fix the bug"
→ claude -p "fix the bug" --agent coder --model claude-haiku-4-5 ...
```
Claude discovers `coder` from `.claude/agents/` or `.agents/agents/` natively. Agent profile body, skills, tools, permissions all handled by Claude.

**Case 2 — Named agent + extra `-s` skills:**
```
meridian run spawn --agent coder -s extra-skill -m claude-haiku-4-5 -p "fix the bug"
→ claude -p "fix the bug" --agents '{"meridian-adhoc": {"prompt": "...", "skills": ["extra-skill", ...]}}' --agent meridian-adhoc ...
```
Build ad-hoc agent JSON with the base agent's config + extra skills. Use `--agents` (inline JSON) + `--agent meridian-adhoc`.

**Case 3 — No agent, just skills:**
```
meridian run spawn -s review -m claude-haiku-4-5 -p "review this"
→ claude -p "review this" --agents '{"meridian-adhoc": {"skills": ["review"]}}' --agent meridian-adhoc ...
```

**Case 4 — No agent, no skills (bare prompt):**
```
meridian run spawn -m claude-haiku-4-5 -p "hello"
→ claude -p "hello" --model claude-haiku-4-5 ...
```
No `--agent` flag. Uses default agent config from Claude.

### OpenCode / Codex / Direct: inject (no change)

These harnesses don't have native skill-aware agent loading. Keep current behavior: read agent body + skill content, compose into prompt.

### Space start/resume (launch.py)

Same pattern. Currently hardcodes `claude --system-prompt <giant_blob>`. Change to:
```
claude --agent <primary_agent_name> --model <model> ...
```
Let Claude load the primary agent profile natively. Space-specific context (space ID, summary, continuation guidance) goes via `--append-system-prompt` or env var (`MERIDIAN_SPACE_PROMPT`).

## Scope

### Changes needed

1. **`HarnessCapabilities`** — add `supports_native_agents: bool`
   - Claude: `True`
   - OpenCode, Codex, Direct: `False`

2. **Claude adapter strategies** — change `"agent"` from `DROP` → `CLI_FLAG --agent`

3. **Claude adapter** — new method to build `--agents` JSON for ad-hoc agents (when extra skills are present)

4. **`_run_prepare.py`** — when harness `supports_native_agents`:
   - Don't inject `agent_body` into composed prompt
   - Don't inject skill content into composed prompt
   - Pass agent name + skill names to `RunParams`
   - If extra skills beyond agent's declared skills: signal ad-hoc agent needed

5. **`launch.py`** — for Claude primary:
   - Pass `--agent <primary_agent_name>` instead of `--system-prompt <blob>`
   - Space context (space ID, summary, continuation) via `--append-system-prompt`

6. **Tests** — update dry-run assertions to expect `--agent` in CLI command for Claude

### Files

- `src/meridian/lib/harness/adapter.py` — add capability flag
- `src/meridian/lib/harness/claude.py` — strategy change + ad-hoc agent JSON builder
- `src/meridian/lib/harness/_strategies.py` — may need new effect type for ad-hoc agent
- `src/meridian/lib/ops/_run_prepare.py` — conditional prompt composition
- `src/meridian/lib/space/launch.py` — primary agent passthrough
- `tests/` — update assertions

## Non-goals

- OpenCode native agent passthrough (no skills field support)
- Codex native agent passthrough (no `--agent` flag)
- Changing how skills are discovered/loaded from disk

# Development Guide: meridian-channel

There are no users and there is no real user data. No need for backwards compatibility. It's okay to completely change the schema to get it into the right shape.

## Philosophy

**Meridian-Channel** is a coordination layer for multi-agent systems—not a file system, execution engine, or data warehouse.

### Core Principles

1. **Harness-Agnostic**: Same `meridian` commands work across Claude, Codex, OpenCode, Cursor, **etc.** (extensible to future harnesses) for both primary agents and subagents, with per-harness adapters
2. **Files as Authority**: All state lives in files under `.meridian/.spaces/<space-id>/`. `space.json` for space metadata, `runs.jsonl` for run events, `sessions.jsonl` for session tracking. Atomic writes via tmp+rename, `fcntl.flock` for concurrency.
4. **Agent Profiles Own Skills**: Static skill definitions in agent profiles, loaded fresh on agent launch/resume
5. **Minimal Constraints**: Agents organize `.meridian/.spaces/<space-id>/fs/` however they want; Meridian provides container only
6. **Result Over Metadata**: Spawn output answers "what happened?" — status, report, done. Input echo, null fields, and ceremony are noise. Detailed metadata (params, logs, tokens) lives in the spawn directory for those who need to dig deeper.

### Architecture

- **Space**: Self-contained agent ecosystem with primary + child agents, shared filesystem. Two states: `active` and `closed`.
- **Primary Agent**: Entry point (any harness), launched via `meridian start`
- **Agent Profile**: YAML markdown defining capabilities, tools, model, skills
- **Skill**: Domain knowledge/capability loaded fresh on launch/resume (survives context compaction)
- **State Layer**: `src/meridian/lib/state/paths.py` (path resolution), `src/meridian/lib/state/run_store.py` (JSONL run events), `src/meridian/lib/space/space_file.py` (space.json CRUD), `src/meridian/lib/space/session_store.py` (session tracking)

## Development

```bash
# Install from source
uv sync --extra dev

# Run tests with token-efficient output (preferred for agents)
uv run pytest-llm

# Type check
uv run pyright
```

### Commit Checkpoints

**Commit after each step that passes tests.** Don't accumulate changes across multiple steps — if a later step breaks things, you lose the ability to roll back cleanly. Each step's commit should be atomic and self-contained:
1. Implement the step
2. Verify tests pass
3. Commit with a descriptive message
4. Move to the next step

### Never Delete Untracked Files

**NEVER delete or remove untracked files without asking the user first.** Untracked files may be the user's in-progress work. If you need to clean up files you believe are stale:
1. Ask the user before deleting
2. If you must proceed, `git stash --include-untracked` first so the work is recoverable
3. When reverting codex agent changes with `git checkout`, check `git status` for untracked files the agent created vs. untracked files that existed before — only clean up agent-created files after confirming with the user

## Current Focus

See `backlog/` for open items and `plans/` for active plans.

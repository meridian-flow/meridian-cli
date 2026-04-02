# Mars Link & Init Redesign — Design Overview

Mars manages agent profiles and skills in a single directory (`.agents/` by default). Multiple tools — Claude Code (`.claude/`), Cursor (`.cursor/`), Codex, Gemini CLI — look for agents/skills in their own tool-specific directories. `mars link` bridges this gap by symlinking the managed content into tool directories. `mars init` scaffolds the managed root.

The current implementation has five structural problems identified by reviewers:
1. Init uses a fragile dot-prefix heuristic to distinguish target dirs from project roots
2. Link has no conflict detection — refuses any existing directory
3. Config mutations bypass the sync lock
4. WELL_KNOWN directories are defined locally, not shared
5. Doctor doesn't validate link health

This redesign addresses all five while adding the conflict-aware merge algorithm that makes `mars link` useful in real projects where tool dirs already have content.

## Architecture

```
project/
├── .agents/           ← managed root (mars init)
│   ├── agents.toml    ← config: sources + settings.links
│   ├── .mars/         ← internal state (lock, cache, sync.lock)
│   ├── agents/        ← managed agent profiles
│   └── skills/        ← managed skills
├── .claude/           ← tool dir (mars link .claude)
│   ├── agents -> ../.agents/agents   ← symlink
│   └── skills -> ../.agents/skills   ← symlink
└── .cursor/           ← tool dir (mars link .cursor)
    ├── agents -> ../.agents/agents
    └── skills -> ../.agents/skills
```

**Key invariant**: The managed root is always a subdirectory of the project root. `root.parent()` is always the project root. This is enforced by init (creates a subdirectory) and validated by root detection (only finds subdirectories with `agents.toml`).

## Component Map

| Component | Doc | What it covers |
|---|---|---|
| Root detection & context | [root-context.md](root-context.md) | `MarsContext`, `WELL_KNOWN`/`TOOL_DIRS`, `find_agents_root` redesign |
| Init command | [init.md](init.md) | `mars init [TARGET] [--link DIR...]`, idempotency, interaction with `--root` |
| Link command | [link.md](link.md) | `mars link <DIR>`, conflict resolution algorithm, `--unlink`, `--force` |
| Config mutations | [config-mutations.md](config-mutations.md) | `ConfigMutation::SetLink`/`ClearLink`, sync lock integration |
| Doctor link checks | [doctor-links.md](doctor-links.md) | Symlink validation, stale entry detection |
| Error model | [error-model.md](error-model.md) | `MarsError::Link` variant, conflict reporting |

## Key Design Decisions

1. **TARGET is a simple directory name, not a path.** `mars init .claude` creates `.claude/` in cwd. No path resolution heuristics. Matches every other CLI tool (git, cargo, uv).

2. **Conflict resolution uses scan-then-act.** The entire target directory is scanned before any filesystem mutation. If any conflict exists, the operation aborts with zero modifications. This is the core safety property.

3. **Link config mutations go through the sync pipeline's `ConfigMutation` enum.** This ensures they run under `sync.lock`, matching every other config mutation in the codebase.

4. **WELL_KNOWN (managed roots) and TOOL_DIRS (linkable dirs) are separate constants.** WELL_KNOWN = `[".agents"]`. TOOL_DIRS = `[".claude", ".cursor"]`. Root detection searches WELL_KNOWN ∪ TOOL_DIRS for `agents.toml`. Init accepts any name. Link accepts any name but warns if not in TOOL_DIRS.

5. **`MarsContext` struct replaces ad-hoc `root.parent()` derivation.** Every command gets both `managed_root` and `project_root` from a single source of truth.

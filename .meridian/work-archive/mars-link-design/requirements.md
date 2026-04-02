# Mars Link & Init Redesign — Requirements

## Context

Mars manages a directory of agent profiles and skills (`.agents/` by default). Multiple tools (Claude Code, Cursor, Codex, Gemini CLI) look for agents/skills in their own directories (`.claude/`, `.cursor/`, etc.). Mars needs to bridge this gap.

Current state: `mars link` was implemented as a simple symlink creator. Reviewer feedback (4 reviewers) exposed fundamental design issues — path heuristics, conflict handling, and the relationship between init/link/root detection.

## Prior Art (from research)

- **Every CLI tool** (`git init`, `cargo init`, `uv init`) treats the path arg as "init IN this directory" — no heuristics.
- **No tool** distinguishes dot-prefixed paths from regular paths.
- **GNU Stow** (1993) — tree-folding symlinks for multi-source directories. Battle-tested.
- **Skillshare (runkids)** — closest to mars link, uses symlinks for multi-target skill distribution.
- **Nobody manages agent profiles** — mars is unique here.

## Core Commands

### `mars init [TARGET] [--link DIR...]`

- `TARGET` — directory name to create (default: `.agents`). Simple name, not a path.
- `--link DIR` — after init, immediately link these directories. Repeatable.
- Examples:
  - `mars init` → creates `.agents/agents.toml`
  - `mars init .claude` → creates `.claude/agents.toml`
  - `mars init --link .claude` → creates `.agents/agents.toml` + links `.claude/`
  - `mars init --link .claude --link .cursor` → creates `.agents/` + links both

### `mars link <DIR> [--force]`

- Links an existing mars-managed directory to another directory.
- Creates symlinks: `<DIR>/agents -> <root>/agents`, `<DIR>/skills -> <root>/skills`
- **Conflict-aware** — checks what's already in `<DIR>` before doing anything.

### `mars link --unlink <DIR>`

- Removes symlinks. Only removes if they point to THIS mars root.

## Link Conflict Resolution

When `mars link .claude` and `.claude/` already has `agents/` or `skills/`:

### Scenario 1: Nothing there
Create symlinks. Done.

### Scenario 2: Already correctly symlinked
No-op. Print info.

### Scenario 3: Symlink pointing elsewhere
Error — refuse. Tell user what it points to.

### Scenario 4: Real directory, no conflicts
Files in `.claude/agents/` that don't exist in `.agents/agents/` → **move into `.agents/agents/`**.
Files that are identical → skip (already present).
Then remove the directory, create symlink.

### Scenario 5: Real directory, with conflicts
Same filename, different content → **error. Do absolutely nothing.**
Print all conflicts. Exit 1. No files modified, created, or moved.

### Scenario 6: --force
Replace whatever's there with symlinks. User explicitly asked for it. Data may be lost.

### Key Principle
**Zero-modification on conflict.** If any conflict is detected, the entire operation is aborted. No partial state. User resolves manually, retries.

## Root Detection & Project Root

### Invariant
The managed root is always a subdirectory of the project root. `root.parent()` is always the project root.

### Auto-detection
Walk up from cwd, check well-known subdirectories at each level:
- `.agents/agents.toml`
- `.claude/agents.toml`
- `.cursor/agents.toml`

First match wins. If multiple exist at the same level, first match wins (may warn in future).

### `--root` flag
Global flag on all commands to explicitly specify the managed directory.

## Settings

```toml
[settings]
links = [".claude", ".cursor"]   # tracked for doctor verification
```

## Doctor Checks

- Each entry in `settings.links` should have valid symlinks for `agents/` and `skills/`
- Symlinks should point to the current mars root
- Warn on stale/broken links

## Reviewer Findings to Address

1. ~~Init dot-prefix heuristic~~ → replaced with simple directory name (no heuristics)
2. ~~root.parent() breaks when root IS project root~~ → enforced invariant: root is always a subdir
3. Unlink should verify target before removing → yes
4. Config lock bypass in persist_link → route through sync lock
5. WELL_KNOWN as shared constant → yes
6. MarsError::Source misused in link.rs → add proper variant
7. Link string normalization → normalize before persisting
8. Doctor link validation → yes

## Non-Goals (v1)

- Multi-source merge into linked directories (files always live in ONE managed root)
- Windows junction/symlink support
- Recursive/nested linking
- Link-time filtering (only link specific agents/skills)

# Task: Fix AGENTS.md in mars-agents

You are updating the developer-facing documentation in `/home/jimyao/gitrepos/mars-agents/AGENTS.md`.

## Context
Read `docs-context.md` (provided via -f) for the full verified behavioral facts from source code.

## Changes Needed

### 1. Sync Pipeline section (line 53)
- `fcntl flock` → "advisory file locking (Unix: `flock`, Windows: `LockFileEx`)" or similar. The locking is now cross-platform.

### 2. Key Modules table (line 147)
- `src/merge/` row says "Three-way merge for conflict resolution" → Fix: "Text merge utilities (conflict markers exist but sync uses source-wins strategy)" or similar. The merge module still exists in code but conflicts are resolved by overwrite, not merge.

### 3. Key types section (line 79)
- `Materialization::Symlink` — note this is only for `.mars/` internal state, targets always get copies

### 4. Sync Pipeline step descriptions
- Verify that step 4/5/6 descriptions match the source-wins behavior. The current text mentions "merge" in some places.

## Style
- Developer-facing. Can reference internal module paths, struct names, etc.
- Keep existing formatting (tables, code blocks, backticks for code refs).

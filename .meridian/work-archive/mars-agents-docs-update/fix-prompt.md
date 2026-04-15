# Task: Fix reviewer findings in mars-agents docs

You are fixing accuracy issues found during review in `/home/jimyao/gitrepos/mars-agents/`.

## Findings to Fix

### 1. AGENTS.md line 79 — Materialization type doesn't exist
The line references `Materialization::Copy` / `Materialization::Symlink` but this type was removed from the codebase. `_self` items are now treated as regular `TargetItem` entries that go through the same install/copy path.

**Fix**: Replace the bullet about Materialization with something accurate. The key types for how items land are `PlannedAction` variants (Install, Overwrite, Skip, Remove, KeepLocal) and `DesiredState` variants (CopyFile, CopyDir, Absent). `_self` local package items are added to the target state as regular TargetItem entries.

Suggested: `- `_self` local package items are added as regular `TargetItem` entries during `build_target` (no special materialization — same install/copy path as dependency items)`

### 2. docs/local-development.md line 125 — _self items NOT symlinked
Current edit says items are "symlinked into the `.mars/` canonical store". They're NOT. Looking at `src/sync/mod.rs:322-338`, local package items are added as `TargetItem` with `SourceOrigin::LocalPackage` and go through normal plan → apply → target sync. No symlinks anywhere.

**Fix**: Remove the symlink mention. State that local package items are discovered, hashed, and installed via the normal sync pipeline. After editing source, run `mars sync` to propagate.

Rewrite the paragraph at line 125 to something like:
"With this, any agents in `agents/` and skills in `skills/` at the project root are automatically installed into the managed root during `mars sync`. Local package items go through the same sync pipeline as dependency items — edit a source file, then run `mars sync` to propagate changes."

### 3. docs/sync-pipeline.md — remaining _self symlink references
Several unchanged sections still mention `_self` symlinks:

- **Line 153**: "Also injects local package symlinks when the project has a `[package]` section — the project's own agents/skills are symlinked into `.mars/` under the `_self` source name"
  → Fix: "Also injects local package items when the project has a `[package]` section — the project's own agents/skills are added to the target state under the `_self` source name (`_self` is the reserved local-project source identifier)."

- **Line 165**: "Symlink | Create relative symlink for `_self` items" — we already fixed this to mention `.mars/` only, but it's still wrong. Remove the Symlink row entirely or change to:
  "Note: `_self` items follow the same Install path as dependency items"

- **Lines 189-195**: The "Local Package Items (`_self`)" section says items are "symlinked into the managed root" and mentions "stale `_self` entries are pruned". Fix: items are installed via the normal sync pipeline, not symlinked.

### 4. docs/lock-file.md line 119 — Symlinked action in lock build table
The table has `Symlinked (_self) | New entry with source checksum`. Since `_self` items go through normal Install, this should be:
`Installed (_self) | New item entry with computed checksums`

Or just remove the special row — `_self` items produce normal Installed outcomes.

## Style
- Keep existing formatting.
- Surgical fixes only — don't rewrite surrounding sections.

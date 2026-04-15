# Mars-agents Documentation Update Context

## Verified Behavioral Facts (from source code reading)

### 1. Conflict Resolution: Source Wins + Warn (NO three-way merge)

**Code:** `src/sync/plan.rs` lines 86-105

When both source and local have changed (Conflict entry), mars ALWAYS overwrites with source content and emits a `conflict-overwrite` warning. There is NO three-way merge attempt. The `PlannedAction::Merge` variant exists in the enum but is never produced by `create()` — conflicts go straight to `PlannedAction::Overwrite`.

Behavior:
- Both agents AND skills use the same strategy: source wins + warn
- `--force` suppresses the warning (since overwrite is expected)
- Without `--force`, warning is: `"{kind} '{name}' has local modifications — overwriting with upstream"`
- The `mars resolve` command still exists for resolving conflict markers (from legacy merge behavior), but new syncs won't produce conflict markers

The old docs described a three-way merge with conflict markers. This is WRONG. Current behavior: source always wins, local modifications are overwritten with a warning.

### 2. No Symlinks — All Copies

All items are installed as copies:
- `.mars/` canonical store gets atomic copies (tmp+rename)
- Target directories (`.agents/`, `.claude/`, etc.) get copies from `.mars/`
- Symlinks in `.mars/` (from `_self` local package items) are FOLLOWED during copy to targets — targets always get real files

The old docs mention symlinks in several places. Fix: all items are copies. Local source edits require `mars sync` to propagate.

**Exception:** `_self` items (local package) ARE symlinked into `.mars/` (not targets). And `mars link` creates directory-level symlinks from tool dirs to the managed root — that's a different concept (tool directory linking, not item materialization).

### 3. Target Divergence Detection

Two places check target divergence:

**During `mars sync`** (target_sync phase):
- For skipped (unchanged) items, compares target file hash against `installed_checksum`
- If divergent: emits `target-divergent` warning, PRESERVES local content
- Message: `"target '{target_name}' item '{path}' diverged from .mars (preserved local content; run 'mars sync --force' or 'mars repair' to reset)"`

**During `mars doctor`** (`check_target_divergence`):
- Iterates all locked items across all configured targets
- Reports missing files: `"missing in target: {path}"`
- Reports modified files: `"divergent in target: {path} (local modifications)"`
- Summary: `"target divergence detected; run 'mars sync --force' to reset modified files or 'mars repair' to restore missing files"`

### 4. Cross-Platform File Locking

Two platform implementations behind `#[cfg]`:
- **Unix:** `libc::flock()` with `LOCK_EX`
- **Windows:** `windows_sys::Win32::Storage::FileSystem::LockFileEx` with `LOCKFILE_EXCLUSIVE_LOCK`

No external crate dependency. `FileLock` struct wraps the fd, releases on drop. Used for `.mars/sync.lock`.

### 5. `mars resolve` Lock Acquisition

`mars resolve` now acquires the sync lock before operating, making concurrent resolve + sync safe.

### 6. `mars check` Dep-Provided Skills

`mars check` no longer false-warns when agents reference skills provided by dependencies (not present locally in the package being checked, but available via the dependency tree).

## Files to Update and What's Wrong

### docs/conflicts.md
- Entire "Content Conflicts (Three-Way Merge)" section is wrong. Replace with source-wins + warn.
- Remove conflict markers section.
- Keep Naming Collisions and Unmanaged File Collisions (correct).

### docs/sync-pipeline.md
- Step 4 diff matrix says "Conflict (needs merge)" → should be "Conflict → source wins overwrite + warn"
- Step 5 lists "Merge" action → remove, conflicts are Overwrite
- Step 5 lists "Symlink" action → clarify: _self symlinks in .mars/ only, targets get copies
- Step 6 is mostly correct but double-check copy language

### docs/lock-file.md
- "three-way diff" reference → fix: dual checksums detect changes, but resolution is overwrite not merge

### docs/commands.md
- `mars resolve` — still valid but context about when markers appear should note they're from legacy/manual edits
- `mars doctor` — add target divergence checking to the checks list

### docs/troubleshooting.md
- Doctor "What it checks" table — add "Target divergence" row
- "Conflict markers" — note these are rare with source-wins strategy

### docs/local-development.md
- "symlinked into the managed root" → fix: _self items symlinked into .mars/, COPIED to targets

### docs/README.md
- Check for symlink references in core concepts. Mostly OK.

### README.md
- Mostly OK, check "How It Works" section.

### AGENTS.md
- "fcntl flock" → note cross-platform (Unix + Windows)
- Module table: "Three-way merge for conflict resolution" → fix: conflict resolution is source-wins

### CHANGELOG.md
- Already exists and looks accurate. No changes needed.

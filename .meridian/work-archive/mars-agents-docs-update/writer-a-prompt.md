# Task: Fix core behavioral docs in mars-agents

You are updating documentation in `/home/jimyao/gitrepos/mars-agents/`. Three files have critically wrong information about conflict resolution and symlinks.

## Context
Read `docs-context.md` (provided via -f) for the full verified behavioral facts from source code.

## Files to Edit

### 1. docs/conflicts.md
The "Content Conflicts (Three-Way Merge)" section (lines 55-114) describes behavior that NO LONGER EXISTS. Replace it entirely:

- **Remove**: three-way merge description, diff matrix showing "Conflict — attempt merge", merge process steps, conflict markers section
- **Replace with**: "Content Conflicts" section explaining source-wins + warn strategy:
  - When both source and local changed, source ALWAYS wins — local modifications are overwritten
  - Mars emits a `conflict-overwrite` warning naming the item
  - No merge, no conflict markers from sync
  - `mars resolve` still exists for manually-edited files with conflict markers
  - `--force` skips the warning (overwrite is already the default behavior; force also overwrites LocalModified entries)
- **Keep**: Naming Collisions section (correct), Unmanaged File Collisions section (correct), Exit Codes section (correct — exit 1 still relevant for unresolved conflict markers from manual edits)
- **Update the diff matrix** to reflect current behavior:
  | Source changed? | Local changed? | Action |
  |---|---|---|
  | No | No | Skip (unchanged) |
  | Yes | No | Update (clean overwrite) |
  | No | Yes | Keep local modification |
  | Yes | Yes | **Source wins** — overwrite + warning |

### 2. docs/sync-pipeline.md
- **Step 4 (Create Plan)**: Update diff matrix — "Conflict (needs merge)" → "Conflict → source wins overwrite + warning"
- **Step 5 (Apply Plan)**: 
  - Remove "Merge | Three-way merge using cached base version" from action table
  - Change "Symlink | Create relative symlink for `_self` items" to note symlinks are in `.mars/` only
  - Or just remove Symlink from the table since it's .mars/ internal detail
- **Step 6 (Sync Targets)**: Already mostly correct about copies. Verify language.
- **Line 58**: "fcntl file locking" → "advisory file locking" (cross-platform now, not fcntl-only)

### 3. docs/lock-file.md
- **Line 80**: "three-way diff" reference → change to just "diff" or "change detection". The dual checksums are used to detect source vs local changes, but resolution is overwrite, not merge.
- **Line 115-118**: Building the Lock table — "Merged / Conflicted" are still valid action names in code, keep them in the table.

## Style
- User-facing documentation. Clear, accurate, no internal implementation details.
- Don't over-explain. State the behavior factually.
- Keep existing formatting conventions (tables, code blocks, headers).

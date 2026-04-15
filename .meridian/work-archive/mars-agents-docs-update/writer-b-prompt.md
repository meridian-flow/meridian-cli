# Task: Fix secondary docs in mars-agents

You are updating documentation in `/home/jimyao/gitrepos/mars-agents/`. These files need doctor/divergence additions and symlink reference cleanup.

## Context
Read `docs-context.md` (provided via -f) for the full verified behavioral facts from source code.

## Files to Edit

### 1. docs/commands.md
- **`mars doctor` section** (line 375-391): Add "Target divergence" to the checks list. Doctor now compares `.agents/` (and other target dirs) against lock checksums, reporting missing and divergent files.
- **`mars resolve` section** (line 212-225): The description is still technically correct (it checks for conflict markers and updates checksums). But add a note that with current source-wins strategy, conflict markers are not produced by `mars sync` — they'd only appear from manual edits or legacy state.

### 2. docs/troubleshooting.md
- **"What it checks" table** (line 14-21): Add a row for target divergence:
  | Target divergence | Each locked item's target copy matches lock checksum |
- **"Conflict markers in files" section** (line 117-123): Add a note that current sync strategy (source wins) does not produce conflict markers. They'd only exist from manual edits or legacy state.

### 3. docs/local-development.md
- **"Local Package Development" section** (line 117-125): Says `_self` items are "symlinked into the managed root". Fix: `_self` items are symlinked into `.mars/` (the canonical store), then COPIED to target directories (`.agents/`, etc.). Users see copies, not symlinks.
- **Line 125**: "via symlinks" → "via copies (symlinked in the canonical store, copied to targets)"

### 4. docs/README.md
- Check for any symlink references in core concepts. The "Managed Layout" section should clarify that .agents/ contains copies, not symlinks. The description "copies managed content into the configured managed root" is correct.
- No major changes expected, just verify accuracy.

### 5. README.md (root)
- The "How It Works" section is mostly correct. Verify the flow diagram description.
- No major changes expected.

## Style
- User-facing documentation. Clear, accurate.
- Keep existing formatting conventions.
- Small, surgical edits — don't rewrite sections that are already correct.

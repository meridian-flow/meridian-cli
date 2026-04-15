# Mars Review Fixes — Design Overview

Fixes for 8 findings from the 6-reviewer assessment of the mars-agents codebase. Organized into Tier 1 (correctness bugs) and Tier 2 (hardening), with Tier 3 structural debt tracked as backlog.

## Problem Summary

The review uncovered safety bugs (symlink canonicalization, path containment), reliability gaps (crash-unsafe sync pipeline, non-atomic directory install), and structural duplication (frontmatter scanning, oversized module). All findings are in code paths that run during normal `mars` operations — they're not edge cases.

## Design Documents

| Doc | Findings | Risk |
|-----|----------|------|
| [canonicalize-safety.md](canonicalize-safety.md) | F4 | Tier 1 — broken symlinks silently unlinked |
| [help-text.md](help-text.md) | F5, F6 | Tier 1 — UX clarity |
| [symlink-containment.md](symlink-containment.md) | F1, F3 | Tier 2 — path escape via symlinked managed root |
| [sync-crash-safety.md](sync-crash-safety.md) | F12, F13 | Tier 2 — crash leaves inconsistent state |
| [cache-locking.md](cache-locking.md) | F14 | Tier 2 — cross-repo cache races |
| [shared-scanning.md](shared-scanning.md) | F19, F20 | Tier 3 — structural debt |

## Key Design Decisions

1. **Canonicalize comparison uses `match` on `(Ok, Ok)` only** — the simplest fix that eliminates the `None == None` bug without changing the comparison model. See [canonicalize-safety.md](canonicalize-safety.md).

2. **Symlink containment validates managed_root ⊂ project boundary** — adds a post-canonicalize check in `MarsContext::new` and symlink-aware scanning in check/doctor. See [symlink-containment.md](symlink-containment.md).

3. **Sync keeps current order, adds collision tolerance** — the current config-first order is correct for recovery. The fix makes `check_unmanaged_collisions` hash-aware so partial prior installs don't block re-sync. See [sync-crash-safety.md](sync-crash-safety.md).

4. **atomic_install_dir uses rename-old-then-rename-new** — shrinks the gap from a potentially long `remove_dir_all` to a single `rename` syscall. See [sync-crash-safety.md](sync-crash-safety.md).

5. **Content-addressed cache entries are immutable** — archive cache already uses `{url}_{sha}` naming, making entries immutable after creation. Git clone cache needs per-entry flock. See [cache-locking.md](cache-locking.md).

## Constraints

- 343 existing tests must stay green
- Follow AGENTS.md principles: resolve-first, atomic writes, no heuristics
- Commit after each logical unit
- Codebase: `/home/jimyao/gitrepos/mars-agents`

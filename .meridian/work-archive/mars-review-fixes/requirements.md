# Mars Review Fixes — Requirements

## Context

6 reviewers across 3 models reviewed the mars-agents codebase after the link/init redesign. 22 findings total. Some already fixed during review. This work item covers the remaining actionable findings, organized by priority.

Codebase: `/home/jimyao/gitrepos/mars-agents` (Rust CLI)

## Already Fixed

- Doctor always says "run repair" → contextual hints per issue type
- Doctor issue strings whitespace artifacts → cleaned
- Help text ".agents root" → "managed root containing mars.toml"
- hash_file silently hashes empty bytes on read error → returns Option, callers treat None as conflict
- Self-link creates circular symlinks → rejected at top of link::run
- Link without mars.toml mutates disk then fails → config existence checked before mutations

## Findings to Fix

### Tier 1: Fix now (correctness + safety)

**F4 (security)**: Unlink canonicalize comparison treats two failures as equal.
`resolved.canonicalize().ok() == expected.canonicalize().ok()` — if both fail, `None == None` is true, so a broken foreign symlink gets removed when the expected managed path is also missing. Only successful canonicalizations should match.

**F5 (design)**: Doctor hints — some issues still lack actionable guidance. Missing skill references should suggest "add a source that provides this skill" not just report the missing name.

**F6 (design)**: check vs doctor distinction unclear from --help. Descriptions should explicitly say when to use which.

### Tier 2: Hardening (security + reliability)

**F1 (security)**: Symlinked managed root or target dir redirects operations outside project. `MarsContext::new` canonicalizes `managed_root`, then derives `project_root` as parent. If `.agents/` is a symlink to `/tmp/evil/`, project_root becomes `/tmp/evil/` parent. Need to validate that the managed root and project root are reasonable (not escaping the expected project boundary).

**F3 (security)**: check/doctor follow symlinks reading arbitrary files. A symlinked skill dir could point to `/etc/` or a huge external tree. Should use `symlink_metadata()` to detect symlinks and either skip or warn, not follow them blindly.

**F12 (arch)**: Sync not retry-safe. Config saved before apply — crash leaves config updated, lock stale, files partially installed. Next run sees new files as unmanaged and blocks. Need journaled/staged apply or save config+lock atomically after apply.

**F13 (arch)**: `atomic_install_dir` deletes old dir before rename. Crash in that gap leaves skill missing. Should rename old to `.old`, rename new in, then delete `.old`.

**F14 (arch)**: Global git cache has no cross-repo locking. Two mars processes in different repos can race on the same cache entry. Need per-cache-entry locking or content-addressed immutable cache.

### Tier 3: Structural debt (defer or do opportunistically)

**F15 (arch)**: Collision rename picks wrong skill for cross-package deps. `rewrite_skill_refs` matches by agent source or takes first candidate — wrong for agents depending on skills from other packages.

**F16 (arch)**: Manifest `DepSpec.items` exists but resolver ignores it. Either remove or implement.

**F17 (arch)**: Error model too coarse. Repair parses error message strings. Should use typed error variants.

**F18 (refactor)**: WELL_KNOWN/TOOL_DIRS in cli/mod.rs — layering issue if non-CLI modules need them.

**F19 (refactor)**: check.rs duplicates frontmatter scanning from doctor.rs. Extract shared scanning.

**F20 (refactor)**: link.rs at 700+ lines. Split into scan/act/mod.

**F21 (refactor)**: dispatch_result 15 identical stanzas. Macro or trait.

## Scope

Design should cover Tier 1 and Tier 2. Tier 3 can be tracked as backlog items.

## Constraints

- 343 tests currently pass — keep them green
- Follow AGENTS.md core principles (resolve-first, atomic writes, no heuristics)
- Commit after each logical unit that passes tests

# Mars Structural Refactor — Design Overview

Entropy-reduction pass on mars-agents. Eight findings from refactor-reviewer p721, covering correctness bugs, duplicated code, dead code, and architectural debt.

## Scope

All changes are internal to the mars-agents codebase (`/home/jimyao/gitrepos/mars-agents`). No public CLI surface changes, no new features. Exit codes unchanged. 352 existing tests must remain green (updated where they exercise dead code paths).

## Design Documents

| Doc | What it covers |
|---|---|
| [typed-errors.md](typed-errors.md) | F17: New `MarsError::UnmanagedCollision` variant, audit of other string-encoded errors |
| [collision-rename.md](collision-rename.md) | F15: Fix `rewrite_skill_refs()` cross-package dep resolution using graph |
| [shared-discovery.md](shared-discovery.md) | F19: Extract `discover_installed()` to deduplicate check.rs/doctor.rs scanning |
| [dead-code-cleanup.md](dead-code-cleanup.md) | Dead `check_collisions()`, `build()` test migration, `DepSpec.items` removal |
| [dispatch-simplify.md](dispatch-simplify.md) | F21: Collapse `dispatch_result()` boilerplate |
| [error-propagation.md](error-propagation.md) | F8: Surface frontmatter rewrite errors instead of swallowing them |

**Not in scope (deferred):**
- F20 (link.rs split) — 788 lines is manageable, no immediate trigger. Defer until link features expand.
- F18 (MarsContext extraction to library) — architectural, no consumer yet. Defer until library API is needed.

## Decision: Defer F20 and F18

Both F20 and F18 are structural improvements that pay off in the future but carry risk now with no immediate benefit. F20 would split link.rs but doesn't reduce complexity — just moves it. F18 would extract MarsContext to a library module but there's no non-CLI consumer. Neither has a correctness issue. Including them would increase the blast radius of this pass for marginal entropy reduction. See [decisions.md](../decisions.md).

## Dependency Order

```
Phase 1: F17 (typed error)          — foundation, repair.rs depends on this
Phase 2: F15 (collision rename)     — independent of F17 but ordered for review clarity
Phase 3: Dead code cleanup          — removes build()/check_collisions()/DepSpec.items
Phase 4: F19 (shared discovery)     — depends on dead code being gone for clean diff
Phase 5: F21 (dispatch simplify)    — independent, ordered last for minimal risk
Phase 6: F8 (error propagation)     — small, independent
```

Each phase produces a commit with all tests passing.

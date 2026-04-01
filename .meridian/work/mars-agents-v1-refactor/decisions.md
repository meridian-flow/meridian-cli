# mars-agents v1 Refactor: Decisions

## D1: Phase ordering — quick wins first, then structural changes

**Decided**: Start with small independent modules (frontmatter, source parser, exit codes) before the big unified pipeline change.

**Alternatives considered**:
- **Risk-first** (unified pipeline first): Front-loads the highest-risk change, but it's harder when target.rs still has 4 responsibilities. More likely to produce a large, hard-to-review phase.
- **Bottom-up** (newtypes first): Systematic but touches many files early, creating churn before the structural fixes that change call sites.

**Why this order**: The frontmatter module extracted in phase 1 reduces target.rs from 4 responsibilities to 3, making the phase 4 pipeline unification cleaner. The source spec parser in phase 2 creates the parsing module that phase 7-8 newtypes build on. Each early phase creates a module the later phases depend on — the order builds infrastructure.

## D2: SyncRequest as the unified entry point, not sync() parameter expansion

**Decided**: Introduce a `SyncRequest` struct that all CLI commands construct, rather than adding more parameters to `sync()`.

**Alternatives considered**:
- **Parameter expansion**: Add `resolution_mode`, `config_mutation`, etc. as parameters to existing `sync()`. Simpler but the function signature grows unbounded and combinations become implicit.
- **Builder pattern**: `SyncPipeline::new().mode(Maximize).mutation(AddSource{...}).run()`. More Rust-idiomatic but introduces a builder that's more complex than needed for 4-5 use cases.

**Why SyncRequest**: It's a data structure that represents intent. CLI constructs it, pipeline consumes it. Invalid combinations (frozen + upgrade) can be validated at construction time. It's also easy to serialize for dry-run reporting.

## D3: Config mutations as enum variants, not pre-applied changes

**Decided**: CLI passes `ConfigMutation` intent (AddSource, RemoveSource, etc.) into the pipeline, which applies it after acquiring flock.

**Why**: This is the only way to fix the TOCTOU race in `mars add`. The config must be loaded, mutated, validated, and written atomically under flock. If CLI pre-applies the mutation, the window between load and flock acquisition allows concurrent clobber.

## D4: Single frontmatter module, not library dependency

**Decided**: Create `src/frontmatter/mod.rs` as an internal module, not extract to a separate crate.

**Why**: The frontmatter parsing is specific to mars-agents' YAML-in-markdown convention. It's 100-200 lines. A separate crate adds dependency management overhead for no reuse benefit.

## D5: Newtype introduction order — SourceName first, then ItemName, then DestPath

**Decided**: Introduce newtypes in order of impact: SourceName (used in config, lock, resolver — most cross-cutting), then ItemName (used in lock, target — medium), then DestPath (used in target, lock — most isolated).

**Why**: SourceName appears in the most IndexMap keys and function signatures. Getting it right first establishes the pattern and fixes the most string confusion. ItemName and DestPath follow the same pattern but touch fewer files.

## D6: Preserve existing test suite, don't rewrite tests

**Decided**: The 281 existing tests serve as regression guards. Each phase adds new tests for the new behavior but does not rewrite existing tests (unless a test directly tests the old API being replaced).

**Why**: Rewriting tests during a refactor is a recipe for introducing bugs in both the code and the tests simultaneously. The existing tests are the safety net.

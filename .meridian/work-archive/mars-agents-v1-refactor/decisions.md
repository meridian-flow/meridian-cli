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

## D7: Review synthesis — override mutation gap (H1)

**Context**: Two reviewers independently flagged that `ConfigMutation::SetOverride`/`ClearOverride` were defined but `execute()` never applied them to `agents.local.toml`.

**Fix applied**: Added `apply_local_mutation()` helper and a step in `execute()` between config load and merge. Override mutations modify `LocalConfig` in memory, then persist `agents.local.toml` at step 15. The fix is documented in sync-pipeline.md.

## D8: Review synthesis — Phase 5 depends on Phase 4 (H2)

**Context**: Reviewer found that resolver-and-errors.md uses `ResolutionMode` (from Phase 4) to determine SHA replay behavior. The overview incorrectly claimed Phase 5 was independent of Phase 4.

**Fix applied**: Phase 5 now explicitly requires Phase 4. Updated overview.md, phase-5 blueprint, and execution rounds.

## D9: Review synthesis — RenameRule semantics (p636 finding 3)

**Context**: Current `mars rename` operates on full managed paths (`agents/coder.md → agents/coder-renamed.md`), but the proposed `RenameRule` uses `ItemName` (just the name part). This narrows the rename semantics.

**Decided**: Keep `RenameRule { from: ItemName, to: ItemName }` for the config-level rename mappings (which operate on item names). The CLI `mars rename` command should translate path-level renames into `ItemName` pairs by stripping the kind prefix. If the user says `agents/coder.md → agents/cool-coder.md`, the RenameRule is `{ from: "coder", to: "cool-coder" }`. The dest path is derived from the renamed name + kind prefix. This is documented in the phase 7 blueprint.

**Why**: Paths are derived from names + kind. Storing full paths in rename rules couples the rule to the filesystem layout. If the layout changes (e.g., skills move to a different prefix), path-based rules break.

## D10: Review synthesis — frontmatter delimiter edge case (p636 finding 4)

**Context**: The frontmatter parser treats any line with trimmed `---` as the closing delimiter, which could match indented `---` inside YAML block scalars.

**Decided**: Accept the current design for Phase 1. In practice, agent frontmatter never contains block scalars with `---` sequences — frontmatter is a flat mapping of simple key-value pairs (name, model, skills list). The column-0-only check is a refinement that can be added later if real content triggers it. Added a `had_frontmatter: bool` field to track round-trip fidelity for empty frontmatter.

## D11: Review synthesis — source parser URL coverage (p636 finding 5)

**Context**: The parser doesn't handle `ssh://`, `git+ssh://`, or ported SSH URLs.

**Decided**: Add these as `SourceFormat` variants in the Phase 2 implementation. The classifier should check for `ssh://` and `git+ssh://` prefixes before the `user@host:path` check. Ported URLs (`ssh://git@host:2222/repo`) normalize to the same canonical form.

## D12: Review synthesis — URL case normalization (p635 M1)

**Context**: `SourceUrl` comparison is case-sensitive, but git hosts like GitHub are case-insensitive for org/repo.

**Decided**: Add `.to_ascii_lowercase()` in the `normalize()` step of the source parser. This makes `GitHub.com/Owner/Repo` and `github.com/owner/repo` produce the same `SourceUrl`, enabling correct `SourceId` deduplication.

## D13: Review synthesis — ResolvedRef version_tag (p636 finding 6)

**Context**: The locked SHA replay path constructs `ResolvedRef` without `version_tag`, but the current struct includes that field.

**Decided**: When replaying from locked SHA, populate `version_tag` from the locked source's version field (prefixed with `v`). This preserves metadata consistency with the normal resolution path.

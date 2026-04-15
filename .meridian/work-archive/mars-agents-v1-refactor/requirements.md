# mars-agents v1 Refactor: Requirements

## Context

mars-agents v0.1.0 is functional — 281 tests passing, 13 CLI commands, full sync pipeline. Smoke testing found 7 bugs (6 fixed). Three independent reviews (structural, deep architectural, SOLID compliance) identified deeper issues that share root causes.

**Codebase location**: `/home/jimyao/gitrepos/mars-agents/`
**Design docs**: `/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-package-management/design/`

## Goal

Refactor mars-agents to eliminate entire classes of bugs through type system enforcement, module boundary clarity, and pipeline unification. Not a rewrite — restructure the existing working code.

## Review Findings (synthesized from 3 reviewers)

### Do-Now: Structural (blocks correctness)

1. **`upgrade` command forks the sync engine** — reimplements resolve/target/diff/plan/apply/lock-write instead of going through sync/mod.rs. Skips flock, drops validation warnings, will keep drifting.
   - Fix: Single `SyncRequest` API with `ResolutionMode` enum. `upgrade` is just `SyncMode::Maximize { targets }`.
   - Source: All 3 reviewers flagged this.

2. **Config load/mutation races with concurrent writers** — CLI loads config before flock, two concurrent `mars add` can clobber each other.
   - Fix: Config must be loaded AFTER flock acquisition. Pass a `ConfigMutation` enum into sync, not a pre-built config.
   - Source: Reviewer 1 (blocking).

3. **Frontmatter rewrite uses substring replace** — `line.replace("plan", ...)` corrupts `planner`, `planning-extended`, comments containing the name. Two incompatible frontmatter implementations (validate/ parses, target/ does string replace).
   - Fix: Single frontmatter module: parse → typed struct → rewrite exact `skills:` entries → serialize back. Both validate and target depend on it.
   - Source: Reviewers 2+3.

4. **Temp files for rewrites not namespaced** — `/tmp/mars-rewrite/<name>.md` shared globally. Concurrent syncs or same-named agents from different sources clobber each other.
   - Fix: In-memory content override on TargetItem, or per-sync temp dir keyed by dest_path.
   - Source: Reviewers 2+3.

5. **Resolver doesn't use locked commit SHA** — `locked.commit` is recorded but ignored on re-resolve. Frozen sync checks for changes but doesn't guarantee same checkout. Force-pushed tags produce different content silently.
   - Fix: Resolver reads `locked.commit` as checkout target when lock exists.
   - Source: Explorer trace + Reviewer 1.

6. **Source spec parser misparses SSH URLs** — splits on last `@` before classifying URL type, turning `git@github.com:org/repo.git` into nonsense.
   - Fix: Dedicated domain parser: classify (path vs shorthand vs URL/SSH) first, then parse version suffix.
   - Source: SOLID reviewer.

7. **Exit code mapping broken** — `main.rs` maps every `Err` to exit 3. Should be per-MarsError-variant.
   - Fix: Match on MarsError variants in dispatch/main.
   - Source: Reviewer 1.

### Do-Soon: Architectural Quality

8. **Stringly-typed identities** — dest_path, source_name, item names are all raw `String`. Rename maps use `IndexMap<String, String>` with ambiguous semantics (item name vs full path).
   - Fix: Newtypes: `SourceName`, `ItemName`, `DestPath`, `RenameRule { from: ItemName, to: ItemName }`.

9. **Dependency identity keyed by name not URL** — two packages with same name but different repo URLs are silently conflated by the resolver.
   - Fix: `PackageId` or `SourceId` containing canonical locator + display name.

10. **Dead `SourceFetcher`/`Fetchers` abstraction** — unused, confusing alongside the live `SourceProvider` trait.
    - Fix: Remove dead code, keep `SourceProvider` or replace with capability-specific traits.

11. **Lock provenance reconstructed heuristically from old lock** — `lock::build` guesses source URLs from `ResolvedRef` + old lock instead of getting them directly.
    - Fix: `ResolvedSourceSpec` carries full provenance through resolution. `lock::build` is a pure function of current inputs.

12. **`build()`/`check_collisions()` API split** — two public APIs, `build()` drops collisions into IndexMap silently, `check_collisions()` can't recover them.
    - Fix: Single collision-safe builder API.

### SOLID Violations (ISP + SoC focus)

13. **sync/target.rs has 4 responsibilities** — discovery, filtering, collision detection, frontmatter rewriting. Each is a reason to change.
    - Fix: Split into focused modules or at least separate functions with clear input/output types.

14. **sync/mod.rs orchestrates + loads config + writes lock + validates** — too many concerns.
    - Fix: After pipeline unification, orchestrator should only sequence steps, not own I/O.

15. **EffectiveConfig bundles too many concerns** — source specs, filter config, rename mappings, settings all in one struct.
    - Fix: Consider separating into `SourcePlan`, `FilterConfig`, `RenameConfig`, `Settings`.

16. **CLI add.rs `parse_source_specifier` mixes 4 concerns** — CLI parsing, URL classification, version extraction, naming policy.
    - Fix: Domain parser module.

17. **SourceProvider trait is fat** — forces implementations to provide `list_versions`, `fetch`, `read_manifest` whether they need them or not.
    - Fix: Capability-specific traits or split into `VersionLister` + `Fetcher` + `ManifestReader`.

## Constraints

- Don't break the working CLI. Refactor incrementally — each phase should leave the crate compiling and tests passing.
- Preserve the existing test suite (281 tests). Add tests for each structural change.
- The crate lives at `/home/jimyao/gitrepos/mars-agents/`. Codex sandbox needs `--sandbox full-access` to write there from meridian-channel spawns.
- Prefer Rust type system enforcement over runtime checks where possible.

## Success Criteria

- `mars upgrade` routes through the same pipeline as `mars sync` (no forked engine)
- Config mutations are atomic — load under flock, validate, write only on success
- Frontmatter rewriting cannot corrupt adjacent skill names
- Frozen sync reproduces exact content via locked commit SHAs
- SSH URLs parse correctly
- Exit codes match spec (0/1/2/3 per error type)
- No stringly-typed identity confusion (newtypes for paths, names, IDs)

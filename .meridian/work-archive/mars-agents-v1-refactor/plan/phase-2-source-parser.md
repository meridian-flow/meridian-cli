# Phase 2: Source Spec Parser

**Fixes:** #6 (SSH URL misparse), #16 (parse_source_specifier mixed concerns)
**Design doc:** [newtypes-and-parsing.md](../design/newtypes-and-parsing.md) §Source Spec Parser
**Risk:** Low — new module, then swap one function in cli/add.rs

## Scope and Intent

Create `src/source/parse.rs` with a format-aware source spec parser that correctly handles SSH URLs by classifying input format BEFORE splitting on `@`. Replace `cli/add.rs::parse_source_specifier` with a call to the new parser.

## Files to Modify

- **`src/source/parse.rs`** (NEW) — `SourceFormat`, `ParsedSourceSpec`, `ParseError`, `classify()`, `split_version()`, `normalize()`, `derive_name()`, `parse()`. ~200 lines + tests.
- **`src/source/mod.rs`** — Add `pub mod parse;`
- **`src/cli/add.rs`** — Replace `parse_source_specifier()` body with call to `source::parse::parse()`. Map `ParsedSourceSpec` → `SourceEntry`.

## Dependencies

- **Requires:** Nothing — independent of phase 1.
- **Produces:** `source::parse` module that phase 7 newtypes build on (parser creates `SourceUrl` values).
- **Independent of:** Phases 1, 3, 4, 5.

## Interface Contract

```rust
// src/source/parse.rs

pub enum SourceFormat { LocalPath, GitHubShorthand, HttpsUrl, SshUrl, BareDomain }

pub struct ParsedSourceSpec {
    pub format: SourceFormat,
    pub raw: String,
    pub url: Option<String>,     // canonical URL (None for paths)
    pub path: Option<PathBuf>,   // local path (None for git)
    pub version: Option<String>, // @version suffix
    pub name: String,            // derived display name
}

pub fn parse(input: &str) -> Result<ParsedSourceSpec, ParseError>;
```

**Note:** Types use `String` not newtypes in this phase. Phase 7 changes `String` → `SourceUrl`/`SourceName`.

## Patterns to Follow

- `src/source/git.rs` for module structure within source/
- Each pipeline step is a pure function — classify, split_version, normalize, derive_name
- Tests: comprehensive table-driven tests covering every format × version combination

## Constraints and Boundaries

- **Out of scope:** Changing `SourceEntry` types (that's phase 7)
- **Out of scope:** Changing how `config::merge` processes source entries
- **Preserve:** Existing behavior for non-SSH URLs (paths, GitHub shorthand, HTTPS)
- **Fix:** SSH URLs (`git@github.com:org/repo.git`) now parse correctly

## Verification Criteria

- [ ] `cargo test` — all 281 existing tests pass
- [ ] `cargo test source::parse` — new parser tests pass:
  - SSH URL: `git@github.com:org/repo.git` → `github.com/org/repo`
  - SSH with version: `git@github.com:org/repo.git@v1.0` → url + version
  - HTTPS and SSH canonicalize to same URL
  - Local path: `./foo@v1` → path includes `@v1` (no version split)
  - GitHub shorthand: `owner/repo@v2` → correct split
- [ ] `cargo clippy -- -D warnings` — clean
- [ ] `mars add git@github.com:org/repo.git` works correctly (smoke test)

## Agent Staffing

- **Implementer:** `coder`
- **Reviewer:** 1 reviewer focused on URL edge cases
- **Tester:** `verifier`

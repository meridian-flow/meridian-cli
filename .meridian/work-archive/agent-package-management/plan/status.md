# Implementation Status

## Phase Progress

| Phase | Status | Coder | Started | Completed | Notes |
|-------|--------|-------|---------|-----------|-------|
| 0 — Scaffold | Not started | — | — | — | — |
| 1a — Error + FS + Hash | Not started | — | — | — | Parallel with 1b |
| 1b — Config + Lock + Manifest | Not started | — | — | — | Parallel with 1a |
| 2a — Discover + Validate | Not started | — | — | — | Parallel with 2b, 3 |
| 2b — Source Fetching | Not started | — | — | — | Parallel with 2a, 3 |
| 3 — Resolve + Merge | Not started | — | — | — | Parallel with 2a, 2b |
| 4 — Sync Pipeline | Not started | — | — | — | Sequential (needs 2a, 2b, 3) |
| 5 — CLI + Integration | Not started | — | — | — | Sequential (needs 4) |

## Blocking Issues

None yet.

## Decisions Log

| # | Decision | Rationale | Phase |
|---|----------|-----------|-------|
| 1 | Use `git2::merge_file()` instead of `threeway-merge` crate | git2 already a dep, avoids extra crate; same libgit2 algorithm | 3 |
| 2 | MVS (minimum version selection) not latest | Reproducible builds without lock; matches Go philosophy | 3 |
| 3 | Base content cached in `.mars/cache/bases/` by installed checksum | Needed for three-way merge base; content-addressed for dedup | 4 |
| 4 | Frontmatter skill rewriting via regex, not YAML parse+serialize | Preserves comments and formatting in agent files | 4 |
| 5 | `SourceEntry` as flat struct with optional fields, not tagged enum | TOML doesn't support serde internal tagging well | 1b |

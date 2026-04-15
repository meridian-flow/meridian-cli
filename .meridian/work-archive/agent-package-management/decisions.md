# Execution Decisions

Decisions made during planning that affect implementation. See also `plan/status.md` for the decision summary table.

## D1: Drop `threeway-merge` crate, use `git2::merge_file()` directly

**Context**: The architecture doc lists both `threeway-merge = "0.2"` and `git2::merge_file()` as options. The review synthesis notes that `git2` is already a dependency.

**Decision**: Use `git2::merge_file()` exclusively. Remove `threeway-merge` from Cargo.toml.

**Rationale**: `git2::merge_file()` provides the same libgit2 three-way merge algorithm. Adding a separate crate for the same functionality adds build weight and a second dependency to audit. The `git2` API is well-documented for this use case.

**Alternative rejected**: `threeway-merge` crate — may not even exist at version 0.2 on crates.io (needs verification during Phase 0). Even if it does, it wraps the same underlying algorithm.

## D2: Minimum version selection (MVS) for resolution

**Context**: The design doc says "URL-based package identity with constraint-based version resolution" but doesn't specify whether to pick minimum or maximum satisfying version.

**Decision**: Minimum version selection when no lock exists. Locked version preferred when constraints still satisfied.

**Rationale**: MVS is deterministic without a lock file — the same constraints always resolve to the same version on any machine. This matches the Go modules philosophy referenced in the design. Users who want the latest version use `@latest` explicitly. This is the conservative choice.

**Alternative rejected**: Latest version selection (npm/cargo style) — requires a lock file for reproducibility. Mars has a lock file, but MVS works even without one, which simplifies `mars add` on a fresh project.

## D3: Base content cache for merge

**Context**: Three-way merge needs a "base" — what mars installed last time. The lock stores checksums but not content. Where does the base content come from?

**Decision**: Cache installed content in `.agents/.mars/cache/bases/{checksum}` after every install/overwrite. Content-addressed by installed checksum.

**Rationale**: The lock's `installed_checksum` uniquely identifies the content mars wrote. Storing a copy keyed by that checksum gives us the merge base for future syncs. Content-addressing means identical content from different items shares storage.

**Alternatives rejected**:
- Re-fetch old version from git: slow, may not be available (tag deleted, force-pushed).
- Store content inline in lock file: lock would be enormous.
- Store content per-item in a separate file: not content-addressed, wastes space on identical content.

**Degradation**: If base cache is missing (first sync, cache corruption), fall back to empty base. This produces more conflict markers but doesn't crash.

## D4: Flat struct for SourceEntry (not serde tagged enum)

**Context**: A source is either git (has `url`) or path (has `path`). The architecture doc uses a tagged enum. TOML serialization of tagged enums is problematic.

**Decision**: Use a flat struct with `url: Option<String>` and `path: Option<PathBuf>`. Validate XOR constraint in `config::merge()`.

**Rationale**: TOML's serde support doesn't handle internally tagged enums well — the serialized output has an extra `type = "git"` field that's not in the design spec. A flat struct with optional fields matches the TOML format users expect and that the design doc shows.

**Alternative rejected**: `#[serde(untagged)]` — works for deserialization but serde's untagged enum deserialization tries each variant in order, producing confusing error messages when both fail.

## D5: Phase structure — 7 phases across 5 rounds

**Context**: The reviewer suggested 4 phases. After analyzing module dependencies more carefully, 7 phases provide better parallelism and right-sizing.

**Decision**: Split into 7 phases with 3 parallel pairs:
- Round 2: Phase 1a + 1b (independent foundation modules)
- Round 3: Phase 2a + 2b + 3 (independent I/O + logic)
- Rounds 4-5: Sequential integration

**Rationale**: Phase 1a and 1b have zero overlap (error/fs/hash vs config/lock/manifest). Phase 2a, 2b, and 3 operate on different concerns (discovery vs fetching vs resolution). Splitting enables parallel execution without merge conflicts. Each phase is completable in a single coder session.

**Alternative rejected**: 4-phase plan from reviewer — Phases 1 and 2 would be too large (each combining unrelated modules), reducing parallelism and increasing risk per phase.

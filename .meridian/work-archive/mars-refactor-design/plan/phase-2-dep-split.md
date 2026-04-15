# Phase 2: A3 — DependencyEntry Split

**Round:** 1 (parallel with Phase 1)
**Risk:** Low — internal type rename, serde-compatible
**Estimated delta:** ~+80 LOC (new types, manifest conversion), ~-20 LOC (removed silent compensation)
**Codebase:** `/home/jimyao/gitrepos/mars-agents/`

## Scope

Split `DependencyEntry` into two types: `InstallDep` (consumer install intent in mars.toml) and `ManifestDep` (package manifest exports). The on-disk TOML format does NOT change (D5). The split is internal — deserialization produces the right type based on context.

## Why This Matters

Currently `load_manifest()` forwards every dependency unchanged, and the resolver silently skips manifest deps without URLs. This hides bugs — a path-only dep in a manifest silently becomes a no-op. The split makes the filtering explicit. Phase 6 (B4) needs `Manifest` to carry `models: IndexMap<String, ModelAlias>`, so getting the Manifest type right now avoids rework.

## Files to Modify

| File | Changes |
|------|---------|
| `src/config/mod.rs` | Rename `DependencyEntry` → `InstallDep`. Add `ManifestDep` struct. Update `Config` to use `InstallDep`. Update `load_manifest()` to convert `InstallDep` → `ManifestDep` with URL-required filter + diagnostic warning for path-only deps. Update `Manifest` struct to use `ManifestDep`. |
| `src/resolve/mod.rs` | Update resolver to use `InstallDep` where it currently uses `DependencyEntry`. Remove the silent skip for deps without URLs (now handled at manifest loading). |
| `src/sync/mutation.rs` | Update `ConfigMutation` to use `InstallDep` instead of `DependencyEntry`. |
| `src/cli/add.rs` | Update to construct `InstallDep` instead of `DependencyEntry`. |
| `src/cli/upgrade.rs` | Same — use `InstallDep`. |
| `src/validate/mod.rs` | Update validation to use `InstallDep`. |

## Interface Contract

```rust
/// Consumer install intent — what goes in [dependencies] of a consumer mars.toml.
pub struct InstallDep {
    pub url: Option<SourceUrl>,
    pub path: Option<PathBuf>,
    pub version: Option<String>,
    pub filter: FilterConfig,
}

/// Package manifest dependency — what a package declares its consumers need.
/// Always has a URL (packages can't declare path deps for consumers).
pub struct ManifestDep {
    pub url: SourceUrl,       // required, not optional
    pub version: Option<String>,
}

/// Package manifest — extracted from a source's mars.toml.
pub struct Manifest {
    pub package: PackageInfo,  // or PackageMetadata if renamed
    pub dependencies: IndexMap<String, ManifestDep>,
    // models field added later in Phase 6 (B4)
}
```

Both `InstallDep` and `ManifestDep` deserialize from the same TOML `[dependencies]` format. The conversion happens in `load_manifest()`:

```rust
pub fn load_manifest(source_root: &Path) -> Result<Option<Manifest>, MarsError> {
    // ... parse Config as before ...
    let deps = parsed.dependencies
        .into_iter()
        .filter_map(|(name, entry)| {
            match entry.url {
                Some(url) => Some((name.to_string(), ManifestDep { url, version: entry.version })),
                None => {
                    // WARNING: path-only manifest dep won't propagate
                    // (Phase 5 will convert this to Diagnostic::Warning)
                    eprintln!("warning: manifest dependency `{name}` has no URL and will not propagate to consumers");
                    None
                }
            }
        })
        .collect();
    Ok(Some(Manifest { package, dependencies: deps }))
}
```

## Constraints

- **No TOML format change.** `InstallDep` must deserialize from the exact same TOML as current `DependencyEntry`.
- **Serde rename:** `InstallDep` uses the same `#[serde(default)]` and field attributes as current `DependencyEntry`.
- **Manifest path-dep filtering:** Currently silent. Make it an eprintln! warning for now — Phase 5 (A5) converts to `Diagnostic::Warning`.
- **Leave `Manifest.models` for Phase 6.** Don't add the models field yet.

## Patterns to Follow

Look at the current `DependencyEntry` at `src/config/mod.rs:33-42`. `InstallDep` is a rename. `ManifestDep` is a subset with `url` as required (not `Option`).

## Verification Criteria

- [ ] `cargo build` compiles cleanly
- [ ] `cargo test` — all existing tests pass
- [ ] `cargo clippy` — no new warnings
- [ ] `load_manifest()` explicitly filters path-only deps with a warning
- [ ] The resolver no longer silently skips deps without URLs (that logic is removed — the filtering happens at manifest load time)
- [ ] TOML deserialization is backwards-compatible — no mars.toml format changes

## Agent Staffing

- **Coder:** 1x gpt-5.3-codex
- **Reviewers:** 1x — correctness focus (verify serde compatibility, no behavior change in resolver)

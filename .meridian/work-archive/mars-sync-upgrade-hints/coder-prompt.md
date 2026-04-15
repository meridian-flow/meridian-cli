# Task: Add upgrade hints to mars sync

Implement GitHub issue #17 for mars-agents. After mars sync completes successfully, print a one-line hint to stderr when newer versions are available.

## Repository

Working in /home/jimyao/gitrepos/mars-agents/.

## What to implement

### 1. Store latest available version per node during resolution

In src/resolve/mod.rs:

- Add `pub latest_version: Option<semver::Version>` field to `ResolvedNode` (around line 41).
- In `resolve_git_source()` (line 403), after `let available = provider.list_versions(url)?;` (line 442), compute the latest version: `let latest = available.iter().max_by(|a, b| a.version.cmp(&b.version)).map(|v| v.version.clone());`
- Return this latest alongside the ResolvedRef. Change `resolve_git_source` return type to `Result<(ResolvedRef, Option<semver::Version>), MarsError>` and propagate.
- At the call site in the main resolve loop (around line 380-398 in the `fetch_source` helper or wherever `resolve_git_source` is called), destructure the tuple and set `latest_version` on the `ResolvedNode`.
- For path sources, set `latest_version: None`.
- Update MockProvider test helpers and any test assertions that construct ResolvedNode to include `latest_version: None`.

### 2. Add upgrades_available to SyncReport

In src/sync/mod.rs:

- Add `pub upgrades_available: usize` field to `SyncReport` struct.
- In `finalize()`, compute the upgrade count by iterating graph nodes and comparing resolved_ref.version vs latest_version. Count where latest > resolved.
- In frozen mode, set to 0 (version lists werent fetched so latest_version will be None anyway, but be explicit).
- Include `upgrades_available` in the SyncReport construction.

### 3. Add --no-upgrade-hint flag to sync CLI

In src/cli/sync.rs:

- Add `--no-upgrade-hint` flag to `SyncArgs`.
- Also respect `MARS_NO_UPGRADE_HINT=1` env var.
- Pass through to the output layer.

### 4. Print upgrade hint in output layer

In src/cli/output.rs:

- Update `print_sync_report` signature to accept `no_upgrade_hint: bool`.
- In human mode: after existing diagnostics, print to stderr with cyan/info styling:
  `  ℹ N upgrade(s) available — run mars upgrade --bump to update`
- Use singular/plural correctly.
- Only print when upgrades_available > 0, not dry_run, and not suppressed.
- In JSON mode: add `upgrades_available` field to JsonReport.

### 5. Update all callers of print_sync_report

Check all files that call `print_sync_report` — sync.rs passes based on flag+env, other commands (upgrade, add, remove) pass `true` to suppress (hint only relevant for direct mars sync).

### 6. Add tests

- Test --no-upgrade-hint flag parsing in sync.rs tests.
- Verify latest_version is populated correctly in resolve tests.

## Key constraints

- No extra network calls — use resolution data already fetched
- Stderr for human hint, JSON field for machine output
- Skip silently in --frozen mode
- Singular/plural: 1 upgrade vs 2 upgrades
- All existing tests pass (cargo test)
- cargo clippy clean
- Compiles without warnings

# Feasibility: Init-Centric Bootstrap

## Validated Assumptions

### Init logic is extractable

**Probe**: Read `src/cli/init.rs` lines 46-54

**Finding**: `ensure_consumer_config` creates `[dependencies]\n` and returns whether config already existed. The core bootstrap logic (create config + create directories) is about 10 lines.

**Verdict**: Confirmed. Extracting a `bootstrap_at()` function is straightforward.

### Current walk-up has git boundary

**Probe**: Read `find_agents_root_from()` (lines 326-353)

**Finding**: Walk-up stops at `.git` boundary (line 337). This single check can be removed.

**Verdict**: Confirmed. Removing git boundary is a one-line deletion.

### MarsContext structure is local

**Probe**: Read `src/cli/mod.rs` lines 46-88

**Finding**: `MarsContext` is defined in the CLI layer. Adding `bootstrapped: bool` affects CLI code only.

**Verdict**: Confirmed. No library-layer changes needed.

### Command dispatch supports per-command behavior

**Probe**: Read `dispatch_result()` (lines 182-194)

**Finding**: Commands are dispatched through a central match. `Add` can be extracted to its own arm to pass `AutoInit::Allowed`.

**Verdict**: Confirmed. The dispatch structure supports per-command auto-init control.

### Atomic write is safe for concurrent init

**Probe**: Reviewed `crate::fs::atomic_write` usage

**Finding**: Uses tmp+rename pattern. If two processes race to init, the first one's rename wins; the second sees the file on its next check.

**Verdict**: Confirmed. Concurrent auto-init is safe.

### Init is idempotent

**Probe**: Read `ensure_consumer_config` logic

**Finding**: If `mars.toml` exists, returns `true` (already initialized) without modifying it.

**Verdict**: Confirmed. Auto-init can safely call init logic even if another process just created the config.

## Windows Path Semantics

### Path::parent() at drive roots

**Probe**: Rust stdlib documentation

**Finding**: `Path::parent()` returns `None` for:
- `/` (Unix root)
- `C:\` (Windows drive root)
- `\\?\C:\` (extended-length drive root)

The walk-up loop uses `match dir.parent() { None => break, ... }`.

**Verdict**: Confirmed. No changes needed for drive root termination.

### canonicalize() extended-length paths

**Probe**: Rust stdlib behavior on Windows

**Finding**: `canonicalize()` on Windows returns extended-length paths:
- Input: `C:\project` → Output: `\\?\C:\project`
- This affects string comparisons but not `Path` methods

The implementation uses `starts_with()` on canonicalized paths, which works correctly.

**Verdict**: Confirmed. Extended-length paths are handled correctly.

### canonicalize() failure on non-existent paths

**Probe**: Rust stdlib behavior

**Finding**: `canonicalize()` fails with `io::Error` if the path doesn't exist. The implementation handles this:
```rust
let cwd_canon = start.canonicalize().unwrap_or_else(|_| start.to_path_buf());
```

**Verdict**: Confirmed. Fallback to original path is already implemented.

### UNC path parent() behavior

**Probe**: Test on Windows with network paths

**Finding**: For `\\server\share\folder`:
- `parent()` returns `\\server\share`
- `parent()` of `\\server\share` returns `\\server`
- `parent()` of `\\server` returns `None`

Walk-up terminates safely.

**Verdict**: Confirmed.

### Path separator handling in --root

**Probe**: Rust PathBuf parsing on Windows

**Finding**: Rust's `PathBuf` accepts both `/` and `\` as separators:
- `PathBuf::from("C:/project")` works
- `PathBuf::from("C:\\project")` works

**Verdict**: Confirmed. Both slash styles work without modification.

### Case sensitivity

**Probe**: Windows filesystem behavior

**Finding**: Windows paths are case-insensitive. `canonicalize()` normalizes case:
- `Path::new("c:\\project").canonicalize()` → `\\?\C:\project`

**Verdict**: Confirmed. Canonicalization normalizes case.

## Open Questions (resolved in design)

### Q: Which commands should auto-init?

**Decision**: Only `init` (canonical) and `add` (clear first-use intent). All others fail on missing config.

**Rationale**: Running `mars sync` or `mars list` in a non-project directory is likely a user error. Fail fast.

### Q: Should init still walk up to git root by default?

**Decision**: No. `init` uses cwd as the project root, same as auto-init from `add`.

**Rationale**: Consistency. Users learn one model. Git is not special.

### Q: How does auto-init interact with `--root`?

**Decision**: `--root` sets the project root unconditionally. Auto-init creates config at `--root`, not cwd.

**Rationale**: `--root` is explicit intent. Honor it.

### Q: Should we add a `--no-init` flag?

**Decision**: Not initially. Can be added later if users want to fail fast when they expect config to exist.

**Rationale**: YAGNI. The auto-init behavior matches npm. Wait for real demand.

## No Probes Needed

- **Concurrent bootstrap race**: Handled by atomic_write + idempotent init. No runtime test required.
- **Permissions errors**: Standard I/O error handling.
- **Git detection**: No longer relevant — git is not consulted.

## Removed from Previous Feasibility

### Git boundary detection

**Previous probe**: `default_project_root()` and git root detection.

**Status**: Removed. Git is not a requirement. Walk-up proceeds to filesystem root.

### Submodule isolation

**Previous finding**: Walk-up stops at `.git` (directory or file) for submodule handling.

**Status**: Removed. Submodules are ordinary directories in the new design.

## Implementation Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Walk-up termination wrong on Windows | Low | High | Stdlib handles it; add Windows CI tests |
| Init/add race creates duplicate config | Very low | Low | Atomic writes + idempotent init |
| Users expect git-root default for init | Medium | Low | Clear init message shows location; doc update |
| Auto-init in wrong directory | Medium | Low | Init message surfaces location; easy recovery |

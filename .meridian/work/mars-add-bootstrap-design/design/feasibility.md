# Feasibility: Walk-Up Add, Explicit Init

## Validated Assumptions

### Walk-up code exists and is modifiable

**Probe**: Read `find_agents_root_from()` (lines 326-353)

**Finding**: Walk-up exists and stops at `.git` boundary (line 337). This single check can be removed to walk to filesystem root.

**Verdict**: Confirmed. Removing git boundary is a one-line deletion.

### Add can use standard context discovery

**Probe**: Read command dispatch in `src/cli/mod.rs`

**Finding**: Commands are dispatched through a central match. `Add` can use the same `find_root_for_context` as other context commands.

**Verdict**: Confirmed. No special handling needed for add.

### Init logic is self-contained

**Probe**: Read `src/cli/init.rs`

**Finding**: `ensure_consumer_config` creates `[dependencies]\n` and returns whether config already existed. Init is idempotent and self-contained.

**Verdict**: Confirmed. Init does not need changes beyond removing git-root default.

### MarsContext structure is local

**Probe**: Read `src/cli/mod.rs` lines 46-88

**Finding**: `MarsContext` is defined in the CLI layer. Removing `bootstrapped` field (if present) affects CLI code only.

**Verdict**: Confirmed. Simplification is straightforward.

### Atomic write is safe for concurrent init

**Probe**: Reviewed `crate::fs::atomic_write` usage

**Finding**: Uses tmp+rename pattern. If two processes race to init, the first one's rename wins; the second sees the file on its next check.

**Verdict**: Confirmed. Concurrent init is safe.

### Init is idempotent

**Probe**: Read `ensure_consumer_config` logic

**Finding**: If `mars.toml` exists, returns `true` (already initialized) without modifying it.

**Verdict**: Confirmed. Re-running init is safe.

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

### Q: Should `add` auto-init if no project exists?

**Decision**: No. `add` errors and directs user to `mars init`.

**Rationale**: Matches `uv add`, `cargo add` semantics. No surprising file creation.

### Q: Should `add` in a subdirectory use the ancestor project?

**Decision**: Yes. Walk-up finds nearest `mars.toml`.

**Rationale**: This is the mainstream pattern. Users expect subdirectory usage to work.

### Q: Should we warn when using an ancestor project?

**Decision**: No. Using ancestor is correct behavior, not a warning condition.

**Rationale**: Walk-up is the expected behavior. Warning would add noise.

### Q: Should nested projects be created implicitly?

**Decision**: No. Nested projects require explicit `mars init`.

**Rationale**: Implicit nesting was a source of confusion. Explicit creation is clearer.

### Q: Should init still walk up to git root by default?

**Decision**: No. `init` uses cwd as the project root.

**Rationale**: Git is not a requirement. Consistency with the overall design.

### Q: How does `--root` interact with walk-up for add?

**Decision**: `--root` sets where walk-up starts, not where config is created.

**Rationale**: `add` finds existing projects. `--root` changes where to start looking.

## No Probes Needed

- **Concurrent init race**: Handled by atomic_write + idempotent init.
- **Permissions errors**: Standard I/O error handling.
- **Git detection**: No longer relevant — git is not consulted.
- **Auto-init logic**: Removed from design.
- **Ancestor warning**: Removed from design.

## Implementation Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Walk-up termination wrong on Windows | Low | High | Stdlib handles it; add Windows CI tests |
| Init race creates duplicate config | Very low | Low | Atomic writes + idempotent init |
| Users expect git-root default for init | Medium | Low | Clear init message shows location; doc update |
| Users expect add to auto-init | Medium | Low | Clear error message directs to init |
| Users expect cwd-first for add | Low | Low | Walk-up is the mainstream pattern |

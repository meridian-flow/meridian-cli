# Feasibility: mars add Bootstrap

## Validated Assumptions

### Current error behavior

**Probe**: Read `src/cli/mod.rs` lines 295-353

**Finding**: `find_agents_root` errors with "no mars.toml found from X up to repository root. Run `mars init` first." when config is missing. The error path is clear and modifiable.

**Verdict**: Confirmed. The error can be replaced with bootstrap logic.

### Walk-up implementation

**Probe**: Read `find_agents_root_from()` (lines 326-353)

**Finding**: Walk-up currently stops at `.git` boundary (line 337). This check can be removed to walk to filesystem root instead.

**Verdict**: Confirmed. Removing the git boundary check is a one-line change.

### Init creates minimal config

**Probe**: Read `src/cli/init.rs` lines 46-54

**Finding**: `ensure_consumer_config` creates `[dependencies]\n` as the initial content. Also creates `.mars/` marker directory.

**Verdict**: Confirmed. Can extract this logic to a shared `bootstrap_project` helper.

### Atomic write safety

**Probe**: Reviewed `crate::fs::atomic_write` usage in init.rs

**Finding**: Uses tmp+rename pattern. Safe for concurrent access.

**Verdict**: Confirmed. Bootstrap is safe even under race conditions.

### MarsContext structure

**Probe**: Read `src/cli/mod.rs` lines 46-88

**Finding**: `MarsContext` has `project_root` and `managed_root`. No `bootstrapped` field currently.

**Verdict**: Adding `bootstrapped: bool` is straightforward. Struct is local to CLI layer.

### Command dispatch structure

**Probe**: Read `dispatch_result()` (lines 182-194)

**Finding**: Commands are dispatched through a central match. `Add` can be extracted to its own arm to pass `auto_bootstrap=true`.

**Verdict**: Confirmed. The dispatch structure supports per-command bootstrap control.

## Open Questions (resolved in design)

### Q: Should `--root` bypass project detection entirely?

**Decision**: Yes. `--root` sets the project root unconditionally. If `mars.toml` is missing and `auto_bootstrap=true`, bootstrap at `--root`.

**Rationale**: If the user says `--root /some/path`, they know what they want. Don't second-guess.

### Q: Should `add` be the only command that auto-bootstraps?

**Decision**: Initially yes. Other context-requiring commands (`sync`, `list`, etc.) should error on missing config.

**Rationale**: `mars sync` in an uninitialized directory is likely a mistake. `mars add` has clear intent to establish a new dependency. Later, if demand exists, extend bootstrap to other commands.

### Q: What happens when user is in a subdirectory of intended project root?

**Decision**: Bootstrap at cwd. The visible message surfaces the location. User can delete and retry from the correct directory.

**Rationale**: There's no universal signal for "project root" without VCS or project-marker heuristics. cwd is simple and user-controlled.

### Q: Should we scan for common project markers?

**Decision**: No. Different ecosystems use different markers (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, etc.). Heuristic scanning adds complexity and edge cases.

**Rationale**: The user's cwd is an explicit choice. Project marker scanning would second-guess that choice.

## No Probes Needed

- **Concurrent bootstrap race**: Handled by atomic_write design. No runtime test required.
- **Permissions errors**: Standard I/O error handling. No special probe needed.
- **Git detection**: No longer relevant — git is not consulted.

## Removed from Previous Feasibility

### Git boundary detection

**Previous probe**: `default_project_root()` and git root detection.

**Status**: Removed. Git is not a requirement. The walk-up proceeds to filesystem root without git boundary checks.

### Submodule isolation

**Previous finding**: Walk-up stops at `.git` (directory or file) for submodule handling.

**Status**: Removed. Submodules are ordinary directories in the new design.

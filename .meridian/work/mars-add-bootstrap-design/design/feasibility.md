# Feasibility: mars add Bootstrap

## Validated Assumptions

### Current error behavior

**Probe**: Read `src/cli/mod.rs` lines 295-353

**Finding**: `find_agents_root` errors with "no mars.toml found from X up to repository root. Run `mars init` first." when config is missing. The error path is clear and modifiable.

**Verdict**: Confirmed. The error can be replaced with bootstrap logic.

### Git boundary detection

**Probe**: Read `default_project_root()` (lines 277-289) and `find_agents_root_from()` (lines 326-353)

**Finding**: Walk-up stops at `.git` (directory or file, handles submodules). `default_project_root()` returns cwd if no git repo found.

**Verdict**: Confirmed. Git boundary is already correctly detected. For bootstrap, we can reuse this logic but distinguish "found git root" from "no git repo".

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

## Open Questions (resolved in design)

### Q: Should `--root` bypass git requirement?

**Decision**: Yes. `--root` is explicit declaration — bootstrap at the specified path regardless of git presence.

**Rationale**: If the user says `--root /some/path`, they know what they want. Don't second-guess.

### Q: Should `add` be the only command that auto-bootstraps?

**Decision**: Initially yes. Other context-requiring commands (`sync`, `list`, etc.) should error on missing config.

**Rationale**: `mars sync` in an uninitialized project is likely a mistake. `mars add` has clear intent to establish a new dependency. Later, if demand exists, extend bootstrap to other commands.

**Implementation note**: Factor bootstrap into a helper, but call it from `add.rs` (or a modified `find_agents_root` with an opt-in parameter), not globally in `find_agents_root`.

**Update after further analysis**: The cleaner approach is to have `find_agents_root` take an optional `auto_bootstrap: bool` parameter. `add` passes `true`, other commands pass `false`. This keeps all root-finding logic centralized.

## No Probes Needed

- **Concurrent bootstrap race**: Handled by atomic_write design. No runtime test required.
- **Permissions errors**: Standard I/O error handling. No special probe needed.
- **Submodule isolation**: Already tested in existing unit tests (lines 553-578).

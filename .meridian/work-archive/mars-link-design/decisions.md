# Decisions

## Phase 1: Error model placement

**Decision**: Added `MarsError::Link` only to `MarsError`, not to `ConfigError` or `LockError`.
**Why**: Link errors are top-level command errors, not config-level or lock-level concerns. The design doc was clear on this — `MarsError::Link` is the semantic variant for link operations.

## Phase 2: MarsContext canonicalization

**Decision**: `MarsContext::new` canonicalizes the managed_root path if the directory exists.
**Why**: Root detection paths like `.agents` need canonical form for reliable comparison in symlink verification (Phase 4). Without canonicalization, `MarsContext::new(PathBuf::from(".agents"))` would store the relative path, and symlink canonicalize comparisons would fail.

## Phase 3: Config persist under existing sync lock

**Decision**: In Phase 4's link command, config persistence happens inline under the already-held sync lock, rather than calling `mutate_link_config` (which acquires its own lock).
**Why**: The link command already holds sync.lock for the scan+act operation. Calling `mutate_link_config` would attempt to re-acquire the same lock, which would either deadlock or succeed depending on OS flock semantics (same-process re-entry). Instead, link does load+mutate+save directly within its existing lock scope. `mutate_link_config` is still available for the unlink path (which doesn't hold its own lock) and for external callers.

## Phase 5: Integration test migration strategy

**Decision**: All integration tests now use `--root <path>/.agents` instead of the old `mars init <path>` positional argument.
**Why**: The redesign changes TARGET from a path to a simple name. Integration tests used full paths like `/tmp/xxx` as the positional arg, which the old heuristic resolved differently depending on whether it started with `.`. Using `--root` is the explicit, non-ambiguous way to specify the managed root path, and matches the design intent.

## Phase 5: init_twice behavior change

**Decision**: Changed `init_twice_fails` integration test to `init_twice_is_idempotent` — second init now succeeds with info message.
**Why**: Design doc specifies idempotent init. Re-running `mars init` when already initialized is a no-op for the init part but still processes `--link` flags. This is important because `mars init --link .claude` should work even if `.agents/` already exists.

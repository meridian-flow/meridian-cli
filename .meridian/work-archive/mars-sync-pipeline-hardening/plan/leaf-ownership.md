# Leaf Ownership Ledger

| EARS ID | Summary | Owning Phase | Status | Tester Lane | Evidence Pointer |
|---|---|---|---|---|---|
| `LOCK-01` | `FileLock::acquire` blocks until exclusive lock acquisition succeeds. | Phase 1 | planned | `@verifier`, `@unit-tester` | — |
| `LOCK-02` | `FileLock::try_acquire` returns `Ok(None)` when another process holds the lock. | Phase 1 | planned | `@verifier`, `@unit-tester` | — |
| `LOCK-03` | Dropping `FileLock` releases the advisory lock automatically. | Phase 1 | planned | `@unit-tester` | — |
| `LOCK-04` | Lock acquisition creates missing parent directories first. | Phase 1 | planned | `@unit-tester` | — |
| `LOCK-05` | Locking compiles and functions on Unix and Windows without elevation. | Phase 1 | planned | `@verifier`, `@smoke-tester` | — |
| `LOCK-06` | Shared lock path uses no Unix-only API directly. | Phase 1 | planned | `@verifier` | — |
| `LOCK-07` | `mars resolve` acquires `sync.lock` before reading or writing `mars.lock`. | Phase 3 | planned | `@verifier`, `@smoke-tester` | — |
| `LOCK-08` | `mars resolve` holds the sync lock through lock-file completion. | Phase 3 | planned | `@verifier`, `@smoke-tester` | — |
| `LOCK-09` | Concurrent `resolve` and `sync` serialize access to `mars.lock`. | Phase 3 | planned | `@smoke-tester` | — |
| `SYM-01` | Non-test code creates no symlinks and removes `PlannedAction::Symlink`. | Phase 2 | planned | `@verifier`, `@smoke-tester` | — |
| `SYM-02` | `_self` items materialize by copy into `.mars/`. | Phase 2 | planned | `@verifier`, `@smoke-tester` | — |
| `SYM-03` | `Materialization` simplification removes the symlink variant. | Phase 2 | planned | `@verifier` | — |
| `SYM-04` | `atomic_symlink()` is removed entirely. | Phase 2 | planned | `@verifier`, `@unit-tester` | — |
| `SYM-05` | `sync/plan.rs` has no symlink branch. | Phase 2 | planned | `@verifier`, `@unit-tester` | — |
| `SYM-06` | `sync/apply.rs` has no symlink handler and no `Symlinked` action. | Phase 2 | planned | `@verifier` | — |
| `SYM-07` | Target sync has no symlink-specific branch and stays robust on unexpected symlinks. | Phase 2 | planned | `@smoke-tester`, `@unit-tester` | — |
| `SYM-08` | Installed-item discovery removes the symlink field. | Phase 2 | planned | `@verifier`, `@unit-tester` | — |
| `SYM-09` | Local source edits require `mars sync` to propagate. | Phase 2 | planned | `@smoke-tester` | — |
| `SKILL-01` | Skill conflicts overwrite instead of merge. | Phase 4 | planned | `@verifier`, `@smoke-tester` | — |
| `SKILL-02` | Skill conflict overwrite emits an explicit warning. | Phase 4 | planned | `@verifier`, `@smoke-tester` | — |
| `SKILL-03` | Agent conflicts still use merge unless `--force` is set. | Phase 4 | planned | `@verifier`, `@smoke-tester` | — |
| `SKILL-04` | Planner branches on `ItemKind` for conflict handling. | Phase 4 | planned | `@verifier`, `@unit-tester` | — |
| `CKSUM-01` | Install, overwrite, and merge outcomes always produce checksums. | Phase 5 | planned | `@verifier`, `@unit-tester` | — |
| `CKSUM-02` | Lock building rejects empty or missing checksums for write-producing outcomes. | Phase 5 | planned | `@verifier`, `@unit-tester` | — |
| `CKSUM-03` | Install and overwrite paths verify written content before success. | Phase 5 | planned | `@verifier`, `@unit-tester` | — |
| `CKSUM-04` | Merge writes compute and carry the merged checksum. | Phase 5 | planned | `@verifier`, `@unit-tester` | — |
| `CKSUM-05` | Sync detects divergence between disk state and lock state at start. | Phase 5 | planned | `@verifier`, `@smoke-tester` | — |
| `CKSUM-06` | Divergence detection emits warnings listing affected items. | Phase 5 | planned | `@verifier`, `@smoke-tester` | — |
| `CKSUM-07` | Divergent managed items are preserved until `--force` or `repair`. | Phase 5 | planned | `@smoke-tester`, `@unit-tester` | — |
| `CKSUM-08` | Target-sync failures are reported while the lock still advances for `.mars/` canonical state. | Phase 5 | planned | `@smoke-tester`, `@verifier` | — |
| `CKSUM-09` | Missing targets self-heal, while divergent targets warn and preserve content. | Phase 5 | planned | `@smoke-tester`, `@unit-tester` | — |
| `PERM-01` | Unix permission handling remains behind `#[cfg(unix)]`. | Phase 5 | planned | `@verifier` | — |
| `PERM-02` | Windows read-only overwrite handling is graceful or clearly reported. | Phase 5 | planned | `@smoke-tester`, `@unit-tester` | — |

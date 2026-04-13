# Architecture: Mars Sync Pipeline Hardening + Windows Support

## Change Map

Six requirements touch four subsystems. The architecture organizes changes by subsystem to minimize cross-cutting risk.

| Subsystem | Files | Requirements | Architecture Doc |
|---|---|---|---|
| File Locking | `src/fs/mod.rs`, `src/cli/resolve_cmd.rs` | R1, R2 | `locking.md` |
| Symlink Elimination | `src/types.rs`, `src/sync/plan.rs`, `src/sync/apply.rs`, `src/sync/mod.rs`, `src/reconcile/fs_ops.rs`, `src/discover/mod.rs`, `src/target_sync/mod.rs` | R3 | `symlink-removal.md` |
| Skill Conflict Handling | `src/sync/plan.rs`, `src/sync/apply.rs` | R4 | `skill-conflicts.md` |
| Checksum Integrity | `src/sync/apply.rs`, `src/sync/diff.rs`, `src/sync/mod.rs`, `src/lock/mod.rs`, `src/target_sync/mod.rs` | R5, R6 | `checksum-integrity.md` |

## Dependency Order

R1 (cross-platform locking) and R3 (symlink removal) are foundational — they change types and APIs that other requirements depend on. R4 and R5 build on the simplified type structure.

```
R1 (locking) ──────────────┐
                            ├── R2 (resolve lock) — trivial after R1
R3 (symlink removal) ──────┤
                            ├── R4 (skill conflicts) — uses simplified planner
                            └── R5 (checksum discipline) — uses simplified apply
R6 (permission check) ────── standalone verification, minimal code change
```

## Refactor Sequencing

R3 (symlink removal) should execute first. It simplifies `PlannedAction`, `Materialization`, `ActionTaken`, and the planner/apply/target-sync code. This simplification makes R4 and R5 cleaner to implement because they operate on fewer variants.

R1 can execute in parallel with R3 since they touch disjoint code (`fs/mod.rs` vs. sync pipeline).

## has_conflict_markers Consolidation

Three implementations exist: `merge/mod.rs` (bytes, line-start aware), `cli/resolve_cmd.rs` (string, naive), `cli/list.rs` (string, naive). The `merge/mod.rs` version is correct (line-start check). The other two should delegate to it. This is a low-risk cleanup that should be done opportunistically when `resolve_cmd.rs` is modified for R2.

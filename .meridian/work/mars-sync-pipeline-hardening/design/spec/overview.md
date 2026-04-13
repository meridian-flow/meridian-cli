# Behavioral Specification: Mars Sync Pipeline Hardening + Windows Support

Six requirement areas (R1–R6) producing behavioral contracts across four subsystems: file locking, sync pipeline, conflict handling, and integrity verification.

## Subsystem Map

| Subsystem | Spec File | Requirements |
|---|---|---|
| File Locking | `locking.md` | R1, R2 |
| Symlink Elimination | `symlink-removal.md` | R3 |
| Skill Conflict Handling | `skill-conflicts.md` | R4 |
| Checksum Integrity | `checksum-integrity.md` | R5, R6 |

## Cross-Cutting Constraints

- CC-1: All non-test code paths must compile on both Unix and Windows (`cargo check --target x86_64-pc-windows-msvc`).
- CC-2: Breaking changes to lock file format, CLI output, or behavior are acceptable (no real users).
- CC-3: `cargo test` must pass on Unix after all changes.

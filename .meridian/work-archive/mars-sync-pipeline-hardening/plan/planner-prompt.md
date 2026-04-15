# Planning Task: Mars Sync Pipeline Hardening + Windows Support

## What You're Planning

Implementation of 6 requirements (R1-R6) and 3 refactors (REF-01, REF-02, REF-03) for the mars-agents Rust codebase at /home/jimyao/gitrepos/mars-agents/.

## Design Package

Read these files in the work directory ($MERIDIAN_WORK_DIR):
- requirements.md — full requirement descriptions
- design/spec/locking.md — LOCK-01 through LOCK-09
- design/spec/symlink-removal.md — SYM-01 through SYM-09
- design/spec/skill-conflicts.md — SKILL-01 through SKILL-04
- design/spec/checksum-integrity.md — CKSUM-01 through CKSUM-09, PERM-01, PERM-02
- design/architecture/overview.md — dependency ordering and file map
- design/architecture/locking.md — platform module pattern, resolve lock
- design/architecture/symlink-removal.md — full removal scope with review findings
- design/architecture/skill-conflicts.md — ItemKind branching in planner
- design/architecture/checksum-integrity.md — mandatory checksums, divergence detection, target sync
- design/refactors.md — REF-01, REF-02, REF-03
- design/feasibility.md — crate comparison (decision: hand-roll)
- decisions.md — D1-D6 (note: D1 says fs2 but architecture overrides to hand-roll)
- plan/pre-planning-notes.md — runtime observations, parallelism hypothesis, edge cases

## Codebase Facts (from pre-planning notes)

- 523 tests currently pass
- Windows cross-compile target available: x86_64-pc-windows-msvc
- All file sizes listed in pre-planning notes
- libc stays (used by hand-rolled Unix locking), windows-sys added for Windows
- CWD is meridian-cli; all cargo commands must run from /home/jimyao/gitrepos/mars-agents/

## Verification Requirements

Each phase must pass:
- cargo build (from /home/jimyao/gitrepos/mars-agents/)
- cargo test
- cargo clippy
- cargo check --target x86_64-pc-windows-msvc (after locking phase adds windows-sys)

## Planning Constraints

The parallelism hypothesis in pre-planning notes proposes 3 rounds / 5 phases. Validate or revise. Key constraint: REF-01 (symlink removal) touches ~12 files — it's large but atomic (compiler enforces exhaustiveness, so partial removal doesn't compile). R1 (locking) is disjoint from REF-01.

Staffing: @coder for implementation, @verifier + @smoke-tester for testing. Smoke testing runs `cargo build && cargo test && cargo clippy` from /home/jimyao/gitrepos/mars-agents/. Verifier checks EARS statement compliance.

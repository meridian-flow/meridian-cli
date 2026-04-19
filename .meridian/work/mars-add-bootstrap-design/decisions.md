# Decisions: Walk-Up Add, Explicit Init

## D1: Init is the only project creation command

**Choice**: Only `mars init` creates `mars.toml`. No other command auto-initializes projects.

**Alternatives rejected**:
- Auto-init from `add` — leads to surprising file creation, nested project confusion
- Per-command bootstrap logic — duplication, inconsistent behavior

**Rationale**: One model for users to learn. Project creation is always explicit.

## D2: Add walks up to find existing project

**Choice**: `mars add` walks from cwd to filesystem root searching for `mars.toml`. Uses nearest config found. Errors if not found.

**Alternatives rejected**:
- Cwd-first: check cwd only, auto-init if missing — diverges from mainstream tooling
- Git-bounded walk-up: stop at `.git` — makes git a requirement

**Rationale**: This matches `uv add`, `cargo add`, and npm semantics. Users expect to be able to run `add` from any subdirectory.

## D3: Add does not create projects

**Choice**: When `mars add` finds no `mars.toml` from cwd to filesystem root, it errors with "Run `mars init` first."

**Supersedes**: Previous design with auto-init at cwd.

**Alternatives rejected**:
- Auto-init at cwd — creates files in unexpected locations
- Auto-init at walk-up root — unclear which directory to pick

**Rationale**: Project creation is `init`'s job. Clear separation of concerns. No surprising file creation.

## D4: Init uses cwd as default target

**Choice**: `mars init` creates project at cwd. `--root <path>` overrides to create at `<path>`.

**Supersedes**: Previous design that walked up to git root.

**Alternatives rejected**:
- Git root as default — git is not a requirement
- Walk-up to find "best" location — heuristic, error-prone

**Rationale**: The user ran the command from this directory. That is their declaration of intent.

## D5: Init does not walk up

**Choice**: `mars init` creates at cwd (or `--root`) exactly. No walk-up.

**Rationale**: Init creates a new project. Walking up would conflate creation with discovery.

## D6: Walk-up boundary is filesystem root

**Choice**: Walk-up continues from cwd to filesystem root. Git boundaries do not stop the walk.

**Supersedes**: Previous design that stopped at `.git` boundary.

**Alternatives rejected**:
- Stop at git root — makes git a requirement
- Stop at common project markers — heuristic, adds complexity

**Rationale**: Git is not a requirement. A valid mars project is simply a directory with `mars.toml`.

## D7: `--root` overrides walk-up start, not target

**Choice**: For context commands (`add`, `sync`, etc.), `--root <path>` sets where walk-up starts. Walk-up still runs from `<path>` to filesystem root.

For `init`, `--root <path>` sets the creation target directly (no walk-up).

**Rationale**: Consistent with different command semantics. Context commands find existing projects; init creates new ones.

## D8: Init creates minimal config

**Choice**: Auto-created `mars.toml` contains only `[dependencies]\n` — no settings, no comments.

**Rationale**: Minimal config is easier to read and modify. Defaults are self-documenting through behavior.

## D9: Init is idempotent

**Choice**: Running `mars init` in an already-initialized directory reports "already initialized" and succeeds.

**Rationale**: Re-running init should not break existing projects.

## D10: Error message directs to init

**Choice**: When context commands find no project, error says:
```
no mars.toml found from <cwd> to filesystem root. Run `mars init` first.
```

**Rationale**: Clear recovery path. User knows exactly what to do.

## D11: Windows compatibility via stdlib

**Choice**: Windows path handling uses Rust stdlib (`Path::parent()`, `canonicalize()`) without platform-specific branches.

**Rationale**: Rust's `Path` abstracts platform differences. Walk-up works identically on Windows, macOS, and Linux.

## D12: Extended-length paths accepted

**Choice**: Paths returned by `canonicalize()` on Windows (e.g., `\\?\C:\project`) are valid project roots.

**Rationale**: Extended-length paths are the canonical form on Windows.

## D13: Both slash styles accepted on Windows

**Choice**: `--root C:/project` and `--root C:\project` both work on Windows.

**Rationale**: Windows supports both separators. Forcing one style adds friction.

## D14: UNC paths supported

**Choice**: UNC paths (`\\server\share\project`) are valid project roots.

**Rationale**: UNC paths are standard Windows paths. No special handling needed.

## D15: Windows tests in CI matrix

**Choice**: CI runs the test suite on Windows (in addition to Linux/macOS).

**Rationale**: Windows support is a hard constraint. Without CI coverage, regressions go undetected.

## D16: Git de-coupling is a separate follow-on track

**Choice**: Removing git assumptions from the codebase (the `.git` check in walk-up, git-root default in init, etc.) is implementation work for this feature but also names a broader follow-on track for auditing other git-coupled behaviors in mars.

**Rationale**: This design specifies git-agnostic behavior. There may be other git assumptions elsewhere.

## D17: Windows compatibility audit is a separate follow-on track

**Choice**: This design specifies Windows-correct walk-up behavior. A repo-wide Windows compatibility audit is a separate effort.

**Rationale**: Walk-up is one feature. Full Windows compatibility covers sync, install, source resolution, and more.

## Removed Decisions (from previous cwd-first design)

The following decisions from the previous cwd-first design are explicitly removed:

- **D18 (Cwd-first for write commands)**: Removed. Add uses walk-up, not cwd-first.
- **D19 (Ancestor warning)**: Removed. No warnings needed — using ancestor is correct behavior.
- **D20 (Dual-path root selection)**: Removed. Single walk-up algorithm for all context commands.
- **D2 (Explicit auto-init allowlist)**: Removed. No commands auto-init.
- **D7 (MarsContext bootstrapped field)**: Removed. No auto-init means no bootstrapped tracking.

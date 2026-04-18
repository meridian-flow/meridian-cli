# Decisions: Init-Centric Bootstrap

## D1: Init is the canonical bootstrap primitive

**Choice**: `mars init` defines bootstrapping. All auto-init paths invoke init semantics, not separate bootstrap logic.

**Alternatives rejected**:
- Per-command bootstrap logic — leads to duplication, inconsistent behavior, hidden special cases
- `add`-specific bootstrap mode — makes `add` magical while other commands behave differently

**Rationale**: One model for users to learn. Auto-init from `add` is a convenience that reuses init, not a separate feature.

## D2: Explicit auto-init allowlist

**Choice**: Commands are explicitly classified as auto-init allowed or init-required. The allowlist is:
- `init` — canonical
- `add` — clear project-setup intent

All other context-requiring commands are init-required.

**Alternatives rejected**:
- Allow auto-init on any command — running `mars sync` in an empty directory should fail, not create a project
- Infer intent from command shape — heuristic, error-prone

**Rationale**: Auto-init is a convenience for first-use, not a general behavior. Only commands with unambiguous project-setup intent qualify.

## D3: Bootstrap at current working directory

**Choice**: When auto-init or explicit init runs, `mars.toml` is created at cwd (or `--root` if specified).

**Supersedes**: Previous design that walked up to git root.

**Alternatives rejected**:
- Git root as default — git is not a requirement, fails in non-git directories
- Walk-up to first common project marker — heuristic, varies by ecosystem

**Rationale**: The user ran the command from this directory. That is their declaration of intent.

**Tradeoff accepted**: If the user is in a subdirectory and wanted the project root elsewhere, the init message shows where config was created. Easy recovery.

## D4: Walk-up to filesystem root (no git boundary)

**Choice**: When searching for existing `mars.toml`, walk from cwd to filesystem root. Git is not consulted.

**Supersedes**: Previous design that stopped at `.git` boundary.

**Alternatives rejected**:
- Stop at git root — makes git a requirement
- Stop at first common project marker — heuristic, adds complexity

**Rationale**: Git is not a requirement. A valid mars project is simply a directory with `mars.toml`. Walk-up finds the nearest one.

## D5: `--root` forces target unconditionally

**Choice**: `mars add --root /path` or `mars init --root /path` uses `/path` as project root, regardless of cwd or walk-up.

**Unchanged from previous design**.

**Rationale**: `--root` is an explicit escape hatch. The user has already decided where the project lives.

## D6: Init creates minimal config

**Choice**: Auto-created `mars.toml` contains only `[dependencies]\n` — no settings, no comments, no managed_root.

**Unchanged from previous design**.

**Rationale**: Minimal config is easier to read and modify. Defaults are self-documenting through behavior.

## D7: MarsContext gains `bootstrapped` field

**Choice**: `MarsContext` includes `bootstrapped: bool` to indicate whether this invocation created the project.

**Alternatives rejected**:
- Separate return value — clutters call sites
- Check filesystem before/after — race-prone, wasteful

**Rationale**: The context already flows through command dispatch. Adding a field is clean and explicit.

## D8: Remove default_project_root git behavior

**Choice**: `default_project_root()` returns cwd directly instead of walking up to git root.

**Alternatives rejected**:
- Keep git-root for init, cwd for add — inconsistent, confusing
- Remove the function entirely — still useful as the default when `--root` is not specified

**Rationale**: Consistency. Both `init` and auto-init use cwd. Git is not special.

## D9: Visible init message

**Choice**: When auto-init occurs, print `initialized <path> with mars.toml` before command output.

**Unchanged from previous design** (was D9: Bootstrap message).

**Rationale**: Since init happens at cwd (which could be "wrong"), the message surfaces mistakes immediately.

## D10: Error message updated for non-git context

**Choice**: When `AutoInit::Required` and no config is found, error says:
```
no mars.toml found from <cwd> to filesystem root. Run `mars init` first.
```

**Supersedes**: Previous error that mentioned "repository root".

**Rationale**: Git is not consulted; the error should not reference it.

## D11: Windows compatibility via stdlib

**Choice**: Windows path handling uses Rust stdlib (`Path::parent()`, `canonicalize()`) without platform-specific branches.

**Unchanged from previous design**.

**Rationale**: Rust's `Path` abstracts platform differences. The init-centric design works identically on Windows, macOS, and Linux.

## D12: Extended-length paths accepted

**Choice**: Paths returned by `canonicalize()` on Windows (e.g., `\\?\C:\project`) are valid project roots. The `\\?\` prefix is not stripped.

**Unchanged from previous design**.

**Rationale**: Extended-length paths are the canonical form on Windows. Stripping them could break long path support.

## D13: Both slash styles accepted on Windows

**Choice**: `--root C:/project` and `--root C:\project` both work on Windows.

**Unchanged from previous design**.

**Rationale**: Windows supports both separators. Forcing one style adds friction without benefit.

## D14: UNC paths supported

**Choice**: UNC paths (`\\server\share\project`) are valid project roots.

**Unchanged from previous design**.

**Rationale**: UNC paths are standard Windows paths. No special handling needed.

## D15: Windows tests in CI matrix

**Choice**: CI runs the test suite on Windows (in addition to Linux/macOS).

**Unchanged from previous design**.

**Rationale**: Windows support is a hard constraint. Without CI coverage, regressions go undetected.

## D16: Git de-coupling is a separate follow-on track

**Choice**: Removing git assumptions from the codebase (the `.git` check in walk-up, git-root default in init, etc.) is implementation work for this feature but also names a broader follow-on track for auditing other git-coupled behaviors in mars.

**Rationale**: This design specifies git-agnostic behavior. The implementation removes the specific checks. But there may be other git assumptions elsewhere in the codebase that should be audited separately.

## D17: Windows compatibility audit is a separate follow-on track

**Choice**: This design specifies Windows-correct bootstrap/walk-up behavior. A repo-wide Windows compatibility audit is named as a separate effort.

**Rationale**: Bootstrap is one command. Full Windows compatibility covers sync, install, source resolution, shell invocations, and more. Scoping that into this feature would delay shipping bootstrap.

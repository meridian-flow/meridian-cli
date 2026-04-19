# Windows Compatibility Behavioral Specification

## Scope Summary

Native Windows support for meridian-cli runtime operations. This spec defines what the system must do on Windows, not how.

## MVP vs Follow-up

**MVP Target**: Web UI researchers on Windows. Requirements marked `[MVP]` are blocking.

**Follow-up**: CLI primary launch with interactive terminal. Requirements marked `[FOLLOW-UP]` are post-MVP.

Requirements without a tag are `[MVP]` by default.

---

## EARS Notation Reference

- **UBIQUITOUS**: The system shall \<requirement\>
- **WHEN**: When \<trigger\>, the system shall \<requirement\>
- **WHERE**: Where \<precondition\>, the system shall \<requirement\>
- **IF-THEN**: If \<condition\>, then the system shall \<requirement\>
- **WHILE**: While \<state\>, the system shall \<requirement\>

---

## 1. Module Import Behavior

### WIN-IMPORT-001 (UBIQUITOUS)
The system shall import successfully on Windows without raising `ModuleNotFoundError` or `ImportError` for Unix-only standard library modules (`fcntl`, `pty`, `termios`, `tty`).

### WIN-IMPORT-002 (UBIQUITOUS)
The system shall defer platform-specific imports to runtime execution paths, not module load time.

---

## 2. Primary Interactive Launch (Follow-up Work)

**MVP Note**: Web UI researchers use pipe-based spawns via the app server. Interactive terminal support via ConPTY/pywinpty is follow-up work for CLI primary launch.

### WIN-LAUNCH-001 (WHEN) [FOLLOW-UP]
When launching a primary interactive harness on Windows, the system shall provide the harness subprocess with a pseudo-terminal that satisfies `sys.stdin.isatty()` and `sys.stdout.isatty()` checks from the child's perspective.

### WIN-LAUNCH-002 (WHEN) [FOLLOW-UP]
When launching a primary interactive harness on Windows, the system shall forward user keyboard input to the harness subprocess in real time.

### WIN-LAUNCH-003 (WHEN) [FOLLOW-UP]
When launching a primary interactive harness on Windows, the system shall mirror harness output to both the user terminal and the `output.jsonl` transcript file simultaneously.

### WIN-LAUNCH-004 (IF-THEN) [FOLLOW-UP]
If the parent terminal is resized during a primary interactive launch on Windows, then the system shall propagate the new dimensions to the child pseudo-terminal.

### WIN-LAUNCH-005 (WHEN) [MVP]
When stdin/stdout are not attached to a terminal on Windows, the system shall fall back to plain subprocess pipes without attempting pseudo-terminal allocation.

### WIN-LAUNCH-006 (WHEN) [FOLLOW-UP]
When the primary launch completes on Windows, the system shall restore the parent terminal to its pre-launch state.

---

## 3. State Locking

### WIN-LOCK-001 (WHILE)
While multiple meridian processes access the same state file on Windows, the system shall prevent concurrent write corruption via exclusive file locking.

### WIN-LOCK-002 (UBIQUITOUS)
The system shall use atomic tmp-and-rename writes on Windows such that incomplete writes never leave corrupt state files.

### WIN-LOCK-003 (IF-THEN)
If a lock acquisition fails on Windows, then the system shall retry or propagate a clear error, not silently skip the lock.

### WIN-LOCK-004 (UBIQUITOUS)
The system shall support reentrant lock acquisition within the same thread on Windows.

---

## 4. Streaming Control and App Transport

### WIN-CONTROL-001 (WHEN)
When a control server is started for a spawn on Windows, the system shall accept control connections over a Windows-compatible transport (named pipe or TCP localhost).

### WIN-CONTROL-002 (WHEN)
When a cancel request is issued to an app-managed spawn on Windows, the system shall route the request to the app server over a Windows-compatible transport.

### WIN-CONTROL-003 (UBIQUITOUS)
The system shall expose the same control API (inject, interrupt, cancel) on Windows as on Unix.

### WIN-CONTROL-004 (WHEN)
When the app server starts on Windows, the system shall bind to a Windows-compatible transport and print connection instructions.

---

## 5. Process Cancellation and Termination

### WIN-TERM-001 (WHEN)
When canceling a CLI-managed spawn on Windows, the system shall terminate the harness subprocess and all its descendants.

### WIN-TERM-002 (WHEN)
When a timeout expires during streaming execution on Windows, the system shall terminate the harness process tree with the same semantics as Unix.

### WIN-TERM-003 (IF-THEN)
If graceful termination fails within the grace period on Windows, then the system shall forcibly kill the process tree.

### WIN-TERM-004 (UBIQUITOUS)
The system shall map Windows process exit codes to the same terminal status categories (succeeded/failed/cancelled) as Unix.

### WIN-TERM-005 (WHEN)
When a parent signal is received during streaming execution on Windows, the system shall initiate spawn shutdown via the same control flow as Unix.

---

## 6. Harness Storage and Session Discovery

### WIN-STORAGE-001 (UBIQUITOUS)
The system shall resolve Claude session storage using Windows-appropriate paths (`%APPDATA%\.claude\projects` or equivalent).

### WIN-STORAGE-002 (UBIQUITOUS)
The system shall resolve Codex session storage using Windows-appropriate paths (`%LOCALAPPDATA%\codex` or equivalent).

### WIN-STORAGE-003 (UBIQUITOUS)
The system shall resolve OpenCode session/log storage using Windows-appropriate paths (`%LOCALAPPDATA%\opencode` or equivalent).

### WIN-STORAGE-004 (WHEN)
When detecting a primary session ID on Windows, the system shall search the Windows-appropriate storage locations.

---

## 7. Child Environment Shaping

### WIN-ENV-001 (UBIQUITOUS)
The system shall include Windows-standard environment variables (`USERPROFILE`, `TEMP`, `TMP`, `HOMEDRIVE`, `HOMEPATH`, `APPDATA`, `LOCALAPPDATA`, `PATHEXT`, `COMSPEC`) in the child environment allowlist on Windows.

### WIN-ENV-002 (WHEN)
When projecting `MERIDIAN_FS_DIR` and `MERIDIAN_WORK_DIR` on Windows, the system shall use forward slashes or Windows-native paths consistently.

### WIN-ENV-003 (IF-THEN)
If a command override is provided via `MERIDIAN_HARNESS_COMMAND` on Windows, then the system shall parse it with Windows command-line quoting semantics.

---

## 8. Symlink-Dependent Behavior

### WIN-SYMLINK-001 (WHERE)
Where symlink creation requires elevated privileges on Windows, the system shall fall back to file copying for Claude session bridging.

### WIN-SYMLINK-002 (IF-THEN)
If symlink creation fails on Windows, then the system shall log a diagnostic and proceed with degraded functionality rather than failing the operation.

---

## 9. Guardrail Script Execution

### WIN-GUARD-001 (WHEN)
When executing guardrail scripts on Windows, the system shall invoke them through an appropriate shell (`cmd.exe` for `.bat`/`.cmd`, PowerShell for `.ps1`, or direct execution for executables).

### WIN-GUARD-002 (IF-THEN)
If a guardrail script lacks an executable extension on Windows, then the system shall attempt execution through a configured fallback interpreter.

---

## 10. Signal Handling in Async Loops

### WIN-SIGNAL-001 (WHEN)
When running the streaming executor on Windows, the system shall handle termination requests through a Windows-compatible mechanism (not `loop.add_signal_handler`).

### WIN-SIGNAL-002 (UBIQUITOUS)
The system shall respond to Ctrl+C (console interrupt) on Windows with the same cancellation flow as Unix SIGINT.

---

## Degraded Behavior (Acceptable for MVP)

### WIN-DEGRADE-001
Documentation workflows that rely on Unix symlinks (linked-agent setup) may require manual file copying on Windows without elevated privileges.

### WIN-DEGRADE-002
Bash-specific guardrail scripts will not execute on Windows unless Git Bash, WSL, or an equivalent is available.

### WIN-DEGRADE-003
CLI primary launch falls back to pipe-based execution (no PTY) until follow-up work adds ConPTY support.

---

## Out of Scope (Follow-up Work)

- CLI primary launch with interactive terminal (ConPTY/pywinpty) — WIN-LAUNCH-001 through WIN-LAUNCH-004, WIN-LAUNCH-006
- `SIGWINCH`-equivalent resize propagation
- Full parity for Unix-only dev helpers (uv-based tooling already cross-platform)
- WSL-specific optimizations
- Windows ARM64 testing
- GUI/tray integration

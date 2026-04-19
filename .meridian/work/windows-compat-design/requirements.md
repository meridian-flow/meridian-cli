# Windows Compatibility Design

## Goal

Produce an approved design package for native Windows support in the current `meridian-cli` repo.

This is no longer a research-only item. The design must be based on the live codebase, not on stale assumptions from `windows-port-research`.

## Scope

- Identify and design fixes for current Windows blockers in live product code.
- Distinguish hard runtime blockers from test/dev/docs friction.
- Define the smallest sound architecture that enables native Windows support without regressing macOS/Linux behavior.
- Replace stale “port the old Unix implementation” framing with current-code seams and target semantics.

## In Scope

- Primary interactive launch portability:
  - PTY/TTY transport
  - terminal resize handling
  - foreground launch behavior
- Streaming/app control-plane portability:
  - per-spawn control channel
  - cross-process cancel/inject
  - app server transport assumptions
- Process termination portability:
  - descendant-tree shutdown semantics
  - background worker cancellation
  - timeout and force-kill behavior
- State-layer portability:
  - locking
  - atomic writes
  - crash-only guarantees on Windows
- Harness storage and session discovery portability:
  - Claude session/project locations
  - Codex session/database locations
  - OpenCode storage/log locations
- Child environment and path portability:
  - env allowlist/pass-through policy
  - Windows path/home/temp conventions
  - path projection into harness launches
- Symlink-dependent behavior:
  - Claude session bridging
  - `.agents` linking / tool integration expectations
- User-facing support surfaces needed for a real Windows story:
  - install/setup docs
  - compatibility statements
  - smoke/dev workflow implications where they block Windows usage

## Out of Scope

- Immediate implementation
- Preserving stale research structure as an artifact contract
- Full parity for every Unix-only dev helper in the first runtime milestone unless it is required for Windows users to operate Meridian itself

## Constraints

- No backward compatibility is required if the schema or abstractions need to change.
- Keep Meridian a thin coordination layer, not a platform-specific workflow engine.
- Files under `.meridian/` remain authoritative state.
- Crash-only guarantees must remain intact after the port.
- Prefer shared cross-platform abstractions over per-harness ad hoc Windows shims.
- Do not port obsolete Unix semantics 1:1 when the live code path already needs better target semantics.
- Design against the current streaming path and current app/control plane, not against removed files or legacy assumptions.

## Current High-Signal Blocker Areas

- `src/meridian/lib/launch/process.py`
  - Unix PTY, fork, session, tty, and resize machinery
- `src/meridian/lib/state/event_store.py`
  - `fcntl` locking
- `src/meridian/lib/state/session_store.py`
  - `fcntl` locking and lease coordination
- `src/meridian/lib/streaming/control_socket.py`
  - Unix-domain control socket server
- `src/meridian/lib/streaming/signal_canceller.py`
  - Unix socket client path and POSIX signal cancellation
- `src/meridian/cli/app_cmd.py`
  - app server bound to a Unix socket
- `src/meridian/lib/harness/claude_preflight.py`
  - symlink-based Claude session bridging
- `src/meridian/lib/harness/{claude,codex,opencode}.py`
  - hardcoded harness storage conventions
- `src/meridian/lib/harness/extractors/{claude,codex,opencode}.py`
  - session/log discovery assumptions
- `src/meridian/lib/launch/env.py`
  - POSIX-centric child env allowlist
- `src/meridian/lib/harness/workspace_projection.py`
  - path projection format assumptions

## MVP Target: Web UI Researchers

**Primary persona**: Biomedical researchers on Windows using the web UI.

**What they need**:
- App server runs on Windows (TCP localhost transport)
- Spawns execute (pipe-based, no PTY needed for web UI spawns)
- Python tools work (state locking, atomic writes)
- State persists correctly (UUID-based layout)

**What they don't need for MVP**:
- Full interactive terminal emulation (ConPTY/pywinpty)
- CLI primary launch with PTY
- Every edge case in interactive terminal handling

**Implication**: REF-001 (terminal transport extraction) becomes follow-up work, not blocking. The critical path is:
- REF-007 (deferred imports) — blocking, must be first
- REF-002 (file locking) — blocking for state operations
- REF-005 (IPC transport) — blocking for app server
- REF-006 (directory fsync guard) — blocking for atomic writes
- REF-003 (termination helper) — needed for spawn lifecycle
- REF-004 (storage paths) — needed for harness discovery

---

## Success Criteria

- The design package explains how Meridian should work on native Windows for:
  - app server transport (TCP localhost)
  - pipe-based spawn execution (non-interactive)
  - state locking and atomic writes
  - harness session discovery and storage resolution
  - child env shaping and projected paths
  - symlink-sensitive behavior
- The spec explicitly separates:
  - must-fix runtime blockers
  - acceptable degraded behavior (interactive terminal)
  - follow-up work (CLI primary launch with PTY)
- The architecture names concrete seams/modules to change and what new abstractions are needed.
- The design explicitly calls out where `windows-port-research` is still useful and where it is stale.
- The result is ready for plan review after user approval, without needing another broad exploratory pass.

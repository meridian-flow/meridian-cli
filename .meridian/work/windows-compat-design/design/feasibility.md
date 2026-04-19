# Feasibility Record

Probe evidence, validated assumptions, and verdicts grounding this design in runtime reality.

## State Layout Alignment

This design aligns with workspace-config-design's UUID model:
- Project UUID in `.meridian/id`
- User state root: `~/.meridian/` (Unix) or `%LOCALAPPDATA%\meridian\` (Windows)
- Project ephemeral state: `~/.meridian/projects/<UUID>/`

No project_key derivation — UUID is generated once and stored.

---

## 1. Research Evidence Disposition

### windows-port-research/pty-audit.md

| Finding | Status | Notes |
|---------|--------|-------|
| PTY path is load-bearing for foreground primary launches | **CURRENT** | Verified in live `process.py` |
| No pty.fork() usage (replaced with openpty+fork) | **CURRENT** | Commit 4fbce6f still applies |
| No existing terminal transport abstraction | **CURRENT** | Still true in live code |
| Session extraction partially coupled to PTY | **CURRENT** | Artifact fallbacks exist |
| pywinpty as ConPTY backend | **CURRENT** | v3.0.0+ is viable |
| ptyprocess for Unix | **DEFER** | Hand-rolled code works; dep optional |
| Initial viewport size before exec is load-bearing | **CURRENT** | Critical for TUI harnesses |
| Live resize forwarding via SIGWINCH | **CURRENT** | No Windows equivalent without ConPTY |

### windows-port-research/termination-audit.md

| Finding | Status | Notes |
|---------|--------|-------|
| killpg helper exists but dormant | **STALE** | Live path is adapter-owned cleanup |
| Live termination is in adapter stop() methods | **CURRENT** | claude_ws, codex_ws, opencode_http |
| psutil already a dependency | **CURRENT** | Used in `liveness.py` |
| terminate_tree() sketch is viable | **CURRENT** | Design adopted |
| kill_grace_secs unused | **STALE** | Field exists but no readers found |
| SignalForwarder has no production callsites | **CURRENT** | Dormant code |

---

## 2. Import-Time Blockers (Verified)

These prevent meridian from importing on Windows at all:

| Module | Line | Import | Blocker Type |
|--------|------|--------|--------------|
| `process.py` | 3 | `import fcntl` | ImportError |
| `process.py` | 6 | `import pty` | ImportError |
| `process.py` | 12 | `import termios` | ImportError |
| `process.py` | 14 | `import tty` | ImportError |
| `event_store.py` | 5 | `import fcntl` | ImportError |
| `session_store.py` | 3 | `import fcntl` | ImportError |

**Verdict**: Must defer these imports before any other work.

---

## 3. Runtime Blockers (Verified)

### Unix Domain Sockets

| Location | API | Windows Alternative |
|----------|-----|---------------------|
| `control_socket.py:32` | `asyncio.start_unix_server()` | `asyncio.start_server()` with TCP localhost |
| `app_cmd.py:45` | `uvicorn.run(uds=...)` | `uvicorn.run(host="127.0.0.1", port=...)` |
| `signal_canceller.py:145` | `aiohttp.UnixConnector()` | `aiohttp.TCPConnector()` |

**Verdict**: TCP localhost for both control sockets and app server on Windows. Same high-level asyncio streams API, minimal platform-specific code. Port numbers persisted to files for address resolution.

### Signal Handling

| Location | API | Windows Behavior |
|----------|-----|------------------|
| `streaming_runner.py:134` | `loop.add_signal_handler()` | NotImplementedError on default event loop |
| `signal_canceller.py:99` | `os.kill(..., SIGTERM)` | SIGTERM not meaningful on Windows |

**Verdict**: Use `signal.signal()` for SIGINT (Ctrl+C). SIGTERM requires workaround or accept Ctrl+C only.

### Process Group Signaling

| Location | API | Windows Behavior |
|----------|-----|------------------|
| `signals.py:37` | `os.getpgid()` | AttributeError |
| `signals.py:38` | `os.killpg()` | AttributeError |

**Verdict**: Replace with psutil-based tree termination. Already validated by `liveness.py` usage.

### fcntl Locking

| Location | API | Windows Alternative |
|----------|-----|---------------------|
| `event_store.py:54,60` | `fcntl.flock()` | `msvcrt.locking()` |
| `session_store.py:293,301,310,361,441,445,606,666` | `fcntl.flock()` | `msvcrt.locking()` |

**Verdict**: `msvcrt.locking()` provides exclusive byte-range locks. Simpler than `fcntl.flock()` semantics but sufficient for current usage.

### Symlinks

| Location | Usage | Windows Behavior |
|----------|-------|------------------|
| `claude_preflight.py:62,67` | `os.symlink()` | Requires SeCreateSymbolicLinkPrivilege |

**Verdict**: Fallback to file copy. Symlinks are optimization, not correctness requirement.

---

## 4. Platform-Specific Storage (Verified)

Harness storage conventions require Windows path resolution:

| Harness | Unix Path | Windows Path (Proposed) |
|---------|-----------|------------------------|
| Claude | `~/.claude/projects/` | `%APPDATA%\.claude\projects\` |
| Codex | `~/.codex/` | `%LOCALAPPDATA%\codex\` |
| OpenCode | `~/.local/share/opencode/` | `%LOCALAPPDATA%\opencode\` |

**Note**: These are Meridian's assumptions about where harnesses store data. Actual harness behavior on Windows not yet verified — harnesses may use different conventions. Design includes abstraction layer to adjust if needed.

---

## 5. Child Environment (Verified)

Current allowlist is POSIX-centric:

```python
_CHILD_ENV_ALLOWLIST = frozenset({
    "PATH", "HOME", "USER", "SHELL", "LANG", "TERM", "TMPDIR",
    "PYTHONPATH", "VIRTUAL_ENV",
})
```

Windows equivalents needed:

| Unix | Windows |
|------|---------|
| `HOME` | `USERPROFILE`, `HOMEDRIVE`+`HOMEPATH` |
| `TMPDIR` | `TEMP`, `TMP` |
| `USER` | `USERNAME` |
| `SHELL` | `COMSPEC` |

**Verdict**: Extend allowlist. Keep Unix vars (cross-platform tools expect them). Add Windows vars.

---

## 6. Command Parsing (Verified)

`shlex.split()` in `context.py` uses POSIX quoting by default.

```python
shlex.split('foo "bar baz"')     # POSIX: ['foo', 'bar baz']
shlex.split('foo "bar baz"', posix=False)  # Windows-ish: ['foo', '"bar baz"']
```

Windows cmd.exe quoting differs from POSIX. For `MERIDIAN_HARNESS_COMMAND`:
- Users on Windows likely write Windows-style commands
- `posix=False` is closer but not exact

**Verdict**: Use `posix=False` on Windows. Document that complex quoting may need adjustment.

---

## 7. Guardrail Execution (Verified)

Current fallback:
```python
if not os.access(script, os.X_OK):
    command = ["bash", str(script)]
```

On Windows:
- `.bat`/`.cmd` → `cmd.exe /c script.bat`
- `.ps1` → `powershell.exe -File script.ps1`
- No extension → try direct, fallback to cmd

**Verdict**: Extend script resolution with Windows-aware dispatch.

---

## 8. Async Event Loop Signal Handlers

`loop.add_signal_handler()` raises `NotImplementedError` on Windows default event loop.

**Alternative approaches**:
1. Use `signal.signal()` from main thread (simpler, cross-platform)
2. Use `ProactorEventLoop` with manual IOCP integration (complex)
3. Accept Ctrl+C only (simplest, may be sufficient)

**Verdict**: Start with `signal.signal()` for SIGINT. Revisit if graceful termination via other means is needed.

---

## 9. pywinpty Viability (Follow-up Work)

**MVP Note**: pywinpty is only needed for CLI primary launch with PTY semantics. Web UI spawns use pipe-based execution.

Checked `pywinpty` GitHub (https://github.com/andfoy/pywinpty):
- v3.0.0 released with ConPTY support
- Maintained by Spyder team
- API: `PtyProcess.spawn()`, `read()`, `write()`, `set_size()`, `isalive()`

**Concerns**:
- Binary wheel availability for all Python versions
- ConPTY requires Windows 10 1809+ (October 2018)

**Verdict**: Viable for Windows 10+ when we add CLI terminal support. For MVP, pipe-based execution works without pywinpty.

---

## 10. Open Questions

### Q1: Harness Windows storage conventions

**Question**: Do Claude, Codex, and OpenCode actually use the proposed Windows paths, or do they have different conventions?

**Impact**: If conventions differ, storage resolution code needs adjustment.

**Recommendation**: Verify against installed harnesses on Windows before implementation. Design includes abstraction layer to accommodate findings.

### Q2: ConPTY resize API

**Question**: Does pywinpty's `set_size()` work reliably for resize propagation, or are there timing/race issues?

**Impact**: Resize fidelity on Windows.

**Recommendation**: Smoke test resize behavior during implementation. Accept degraded resize as fallback.

### Q3: Named pipe vs TCP for control socket

**Question**: Does asyncio's named pipe support work reliably on Windows, or should we use TCP for everything?

**Impact**: IPC transport decision.

**Verdict (CLOSED)**: Use TCP localhost for both control sockets and app server on Windows.

Python's asyncio does not provide a high-level streams API for Windows named pipes. The only named pipe support is via low-level protocol-based APIs (`loop.start_serving_pipe()`, `loop.create_pipe_connection()`), which require writing protocol classes instead of using `StreamReader`/`StreamWriter`. There is no `asyncio.start_server(..., pipe=...)` parameter — this was a design doc error.

TCP localhost (`127.0.0.1:<port>`) uses the same `asyncio.start_server()` / `asyncio.open_connection()` API as Unix, works with uvicorn and aiohttp out of the box, and aligns with Meridian's "simplest thing that works" philosophy. The latency difference between TCP localhost and named pipes is negligible for control traffic.

### Q4: Atomic write durability on Windows

**Question**: Does the current `atomic.py` implementation work correctly on Windows?

**Verdict (CLOSED)**: Core pattern works; directory fsync requires platform guard.

The atomic write pattern in `atomic.py` uses:
1. `tempfile.mkstemp()` — works on Windows
2. `os.fsync(handle.fileno())` — works on Windows
3. `os.replace(tmp_path, path)` — atomic on Windows (unlike `os.rename()` which fails if target exists)
4. `_fsync_directory(path.parent)` — **fails on Windows**

The directory fsync uses `os.open(path, os.O_RDONLY | os.O_DIRECTORY)` which fails on Windows:
- `os.O_DIRECTORY` does not exist (code already guards with `hasattr`)
- More fundamentally, Windows does not allow opening a directory as a file — `os.open()` will fail

**Recommendation**: Wrap `_fsync_directory()` in a platform guard:

```python
def _fsync_directory(path: Path) -> None:
    if IS_WINDOWS:
        # Windows NTFS is journaling; directory entry is durable after os.replace()
        # No equivalent to POSIX directory fsync
        return
    # ... existing Unix implementation
```

This is acceptable because:
- NTFS is a journaling filesystem that ensures metadata consistency
- `os.replace()` is atomic on Windows
- The directory fsync is a belt-and-suspenders measure on Unix for power-loss scenarios
- Meridian's crash-only design already tolerates incomplete writes via event store reconciliation

---

## Summary Verdicts

| Area | Feasibility | Confidence | MVP |
|------|-------------|------------|-----|
| Import-time fixes | Straightforward | High | ✓ |
| File locking | Straightforward (msvcrt) | High | ✓ |
| Process termination | Straightforward (psutil) | High | ✓ |
| Terminal transport | Moderate (pywinpty) | Medium-High | Follow-up |
| IPC transport | Straightforward (TCP localhost) | High | ✓ |
| Atomic writes | Straightforward (skip dir fsync) | High | ✓ |
| Signal handling | Moderate (signal.signal) | Medium | ✓ |
| Symlink fallback | Straightforward | High | ✓ |
| Storage paths | Needs verification | Medium | ✓ |
| Guardrail execution | Straightforward | High | ✓ |
| State layout (UUID) | Straightforward | High | ✓ |

**MVP path**: All items marked ✓ enable web UI researchers on Windows. Terminal transport is follow-up work for CLI primary launch.

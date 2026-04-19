# Windows Compatibility Technical Architecture

## Overview

This architecture defines the smallest sound cross-platform abstraction set for native Windows support. The design favors thin platform adapters over deep Windows-specific rewrites, and shared abstractions over per-harness shims.

## State Layout Alignment

This design aligns with workspace-config-design's UUID model:

- **Project identity**: UUID in `.meridian/id`, generated on first write
- **User state root**: `~/.meridian/` (Unix) or `%LOCALAPPDATA%\meridian\` (Windows)
- **Project ephemeral state**: `~/.meridian/projects/<UUID>/` — spawns, sessions, cache
- **No derivation**: No git remote hashing, no path normalization

See workspace-config-design for the full model.

## MVP vs Follow-up

**MVP**: Sections 1, 3, 4, 5, 6, 7, 8, 9, 10, 11 — enable web UI researchers on Windows.

**Follow-up**: Section 2 (Interactive Terminal Transport) — CLI primary launch with ConPTY.

---

## 1. Platform Detection and Conditional Import

### Module: `src/meridian/lib/platform/__init__.py` (new)

```python
import sys
IS_WINDOWS = sys.platform == "win32"
IS_POSIX = sys.platform != "win32"
```

### Pattern: Lazy Platform Imports

All Unix-only imports (`fcntl`, `pty`, `termios`, `tty`) must be deferred to function-level or wrapped in platform guards. No top-level imports of these modules.

**Before (import-time blocker):**
```python
import fcntl  # Fails on Windows at import time
```

**After:**
```python
def lock_file(path):
    if IS_WINDOWS:
        from meridian.lib.platform.locking import win_lock_file
        return win_lock_file(path)
    else:
        import fcntl
        # ... Unix path
```

---

## 2. Interactive Terminal Transport (Follow-up Work)

**MVP Note**: Web UI spawns use pipe-based execution. This section is follow-up work for CLI primary launch with interactive terminal.

### Module: `src/meridian/lib/launch/terminal/` (new directory)

Extract terminal transport from `process.py` into a protocol-based abstraction.

```
src/meridian/lib/launch/terminal/
    __init__.py           # Protocol export
    protocol.py           # InteractiveTransport protocol
    posix_transport.py    # Unix PTY implementation (current code)
    windows_transport.py  # ConPTY/pywinpty implementation
    pipe_fallback.py      # Non-TTY fallback (shared)
```

### Protocol: `InteractiveTransport`

```python
from typing import Protocol, Callable
from pathlib import Path
from dataclasses import dataclass

@dataclass(frozen=True)
class TransportResult:
    exit_code: int
    child_pid: int | None

class InteractiveTransport(Protocol):
    def run(
        self,
        *,
        command: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        output_log_path: Path,
        on_child_started: Callable[[int], None] | None = None,
    ) -> TransportResult: ...
```

### Implementation: `PosixInteractiveTransport`

Move current `_run_primary_process_with_capture()` and `_copy_primary_pty_output()` code here. Keep:
- `pty.openpty()` + `os.fork()` pattern
- `termios`/`tty` raw mode handling
- `SIGWINCH` forwarding
- `select.select()` loop

### Implementation: `WindowsInteractiveTransport`

Use `pywinpty` for ConPTY-backed pseudo-terminal:

```python
import pywinpty

class WindowsInteractiveTransport:
    def run(self, *, command, cwd, env, output_log_path, on_child_started=None):
        pty_process = pywinpty.PtyProcess.spawn(
            command,
            cwd=str(cwd),
            env=env,
        )
        # Initial size sync
        cols, rows = _get_console_size()
        pty_process.set_size(cols, rows)
        
        # ... read/write loop with output mirroring
        # ... resize handling via console API
```

**Dependency**: Add `pywinpty>=2.0.0` as Windows-only optional dependency.

### Factory: `get_interactive_transport()`

```python
def get_interactive_transport() -> InteractiveTransport:
    if IS_WINDOWS:
        from .windows_transport import WindowsInteractiveTransport
        return WindowsInteractiveTransport()
    else:
        from .posix_transport import PosixInteractiveTransport
        return PosixInteractiveTransport()
```

---

## 3. File Locking Abstraction

### Module: `src/meridian/lib/platform/locking.py` (new)

```python
from contextlib import contextmanager
from pathlib import Path
import threading
from typing import IO, Iterator

_THREAD_LOCAL = threading.local()

@contextmanager
def lock_file(lock_path: Path) -> Iterator[IO[bytes]]:
    """Cross-platform exclusive file lock with reentrancy."""
    if IS_WINDOWS:
        yield from _win_lock_file(lock_path)
    else:
        yield from _posix_lock_file(lock_path)

def _posix_lock_file(lock_path: Path) -> Iterator[IO[bytes]]:
    import fcntl
    # Current event_store.py implementation
    ...

def _win_lock_file(lock_path: Path) -> Iterator[IO[bytes]]:
    import msvcrt
    # msvcrt.locking(fd, msvcrt.LK_NBLCK, size) pattern
    # Or: portalocker library for cleaner API
    ...
```

### Update: `event_store.py` and `session_store.py`

Replace direct `fcntl` calls with platform abstraction:

```python
from meridian.lib.platform.locking import lock_file
# Remove: import fcntl
```

**Decision**: Use `msvcrt.locking()` directly rather than adding `portalocker` dependency. `msvcrt` is stdlib on Windows.

---

## 4. IPC Transport Abstraction

### Module: `src/meridian/lib/platform/ipc.py` (new)

Unix domain sockets have no direct Windows equivalent. Transport options:

1. **Named pipes** (`\\.\pipe\meridian-spawn-{id}`) — native Windows IPC, but asyncio only exposes low-level protocol-based APIs (`loop.start_serving_pipe()`, `loop.create_pipe_connection()`), not the high-level streams API used by `start_unix_server()`. There is no `asyncio.start_server(..., pipe=...)` parameter.
2. **TCP localhost** (`127.0.0.1:<port>`) — uses the same high-level asyncio streams API on both platforms, works with uvicorn, aiohttp, and standard HTTP tooling.

**Decision**: TCP localhost for both control socket and app server on Windows. The high-level streams API is identical to Unix, minimizing platform-specific code paths. Port allocation uses ephemeral ports (kernel-assigned) with the port number persisted to a known file path.

**Security**: Binding to `127.0.0.1` only accepts connections from the same machine — equivalent security posture to Unix domain sockets for local-only traffic. No authentication is added; the threat model is the same as Unix (local user can access their own spawns).

### Transport Selection Protocol

```python
# src/meridian/lib/platform/ipc.py

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

@dataclass(frozen=True)
class ServerAddress:
    """Platform-agnostic server address."""
    unix_path: Path | None = None  # Unix domain socket path
    tcp_port: int | None = None    # TCP localhost port

    def to_uvicorn_kwargs(self) -> dict[str, object]:
        if self.unix_path is not None:
            return {"uds": str(self.unix_path)}
        if self.tcp_port is not None:
            return {"host": "127.0.0.1", "port": self.tcp_port}
        raise ValueError("No address configured")

    def to_aiohttp_connector(self) -> object:
        import aiohttp
        if self.unix_path is not None:
            return aiohttp.UnixConnector(path=str(self.unix_path))
        return aiohttp.TCPConnector()

    def to_http_url(self, path: str) -> str:
        if self.unix_path is not None:
            return f"http://localhost{path}"
        if self.tcp_port is not None:
            return f"http://127.0.0.1:{self.tcp_port}{path}"
        raise ValueError("No address configured")
```

### Control Socket Server

The control socket server uses platform dispatch with the same asyncio streams API.

State paths use the user state root resolved via project UUID:
- Unix: `~/.meridian/projects/<UUID>/spawns/<spawn_id>/`
- Windows: `%LOCALAPPDATA%\meridian\projects\<UUID>\spawns\<spawn_id>\`

```python
# src/meridian/lib/streaming/control_socket.py

class ControlSocketServer:
    def __init__(self, spawn_id: SpawnId, user_state_root: Path, manager: SpawnManager):
        self._spawn_id = spawn_id
        self._user_state_root = user_state_root  # e.g., ~/.meridian/projects/<UUID>/
        self._manager = manager
        self._server: asyncio.AbstractServer | None = None
        self._address: ServerAddress | None = None

    async def start(self) -> None:
        spawn_dir = self._user_state_root / "spawns" / self._spawn_id
        spawn_dir.mkdir(parents=True, exist_ok=True)
        
        if IS_WINDOWS:
            # Bind to ephemeral port, persist to file
            self._server = await asyncio.start_server(
                self._handle_client, host="127.0.0.1", port=0
            )
            port = self._server.sockets[0].getsockname()[1]
            self._address = ServerAddress(tcp_port=port)
            self._write_port_file(spawn_dir, port)
        else:
            # Unix domain socket at spawn artifact path
            socket_path = spawn_dir / "control.sock"
            socket_path.unlink(missing_ok=True)
            self._server = await asyncio.start_unix_server(
                self._handle_client, path=str(socket_path)
            )
            self._address = ServerAddress(unix_path=socket_path)

    def _write_port_file(self, spawn_dir: Path, port: int) -> None:
        port_file = spawn_dir / "control.port"
        port_file.write_text(f"{port}\n")
```

### Control Socket Client

Clients resolve the address from the port file (Windows) or socket path (Unix). The `user_state_root` is the project-specific ephemeral state directory (`~/.meridian/projects/<UUID>/`), resolved via the project UUID in `.meridian/id`.

```python
# src/meridian/lib/platform/ipc.py

def resolve_control_address(user_state_root: Path, spawn_id: SpawnId) -> ServerAddress:
    """Resolve the control socket address for a spawn.
    
    Args:
        user_state_root: Project-specific state dir, e.g., ~/.meridian/projects/<UUID>/
        spawn_id: The spawn to connect to
    """
    spawn_dir = user_state_root / "spawns" / spawn_id

    if IS_WINDOWS:
        port_file = spawn_dir / "control.port"
        if port_file.exists():
            port = int(port_file.read_text().strip())
            return ServerAddress(tcp_port=port)
        raise FileNotFoundError(f"Control port file not found: {port_file}")

    socket_path = spawn_dir / "control.sock"
    if socket_path.exists():
        return ServerAddress(unix_path=socket_path)
    raise FileNotFoundError(f"Control socket not found: {socket_path}")


async def connect_to_control(address: ServerAddress) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to a control socket server."""
    if address.unix_path is not None:
        return await asyncio.open_unix_connection(path=str(address.unix_path))
    if address.tcp_port is not None:
        return await asyncio.open_connection(host="127.0.0.1", port=address.tcp_port)
    raise ValueError("No address configured")
```

### App Server Transport

The app server is user-global (serves multiple projects), so it lives at the user state root level rather than per-project:
- Unix: `~/.meridian/app.sock`
- Windows: `%LOCALAPPDATA%\meridian\app.port`

```python
# src/meridian/cli/app_cmd.py

def run_app(uds: str | None = None, port: int | None = None, ...) -> None:
    # User state root: ~/.meridian/ or %LOCALAPPDATA%\meridian\
    user_root = resolve_user_state_root()

    if IS_WINDOWS:
        # TCP on Windows, optionally user-specified port
        resolved_port = port or _find_ephemeral_port()
        _write_app_port_file(user_root, resolved_port)
        print(f"Starting meridian app on http://127.0.0.1:{resolved_port}")
        uvicorn.run(app, host="127.0.0.1", port=resolved_port, log_level="info")
    else:
        # Unix domain socket on POSIX
        socket_path = Path(uds or str(user_root / "app.sock"))
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        socket_path.unlink(missing_ok=True)
        print(f"Starting meridian app on unix socket: {socket_path}")
        uvicorn.run(app, uds=str(socket_path), log_level="info")


def _find_ephemeral_port() -> int:
    """Get an available ephemeral port from the OS."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _write_app_port_file(user_root: Path, port: int) -> None:
    port_file = user_root / "app.port"
    user_root.mkdir(parents=True, exist_ok=True)
    port_file.write_text(f"{port}\n")
```

### Signal Canceller Cross-Process Cancel

```python
# src/meridian/lib/streaming/signal_canceller.py

async def _cancel_app_spawn_over_http(self, spawn_id: SpawnId) -> CancelOutcome:
    # App server address is at user root level, not per-project
    address = resolve_app_address(self._user_root)
    connector = address.to_aiohttp_connector()
    url = address.to_http_url(f"/api/spawns/{spawn_id}/cancel")

    async with aiohttp.ClientSession(connector=connector, timeout=...) as session:
        async with session.post(url) as response:
            # ... existing response handling


def resolve_app_address(user_root: Path) -> ServerAddress:
    """Resolve the app server address.
    
    Args:
        user_root: User state root, e.g., ~/.meridian/ or %LOCALAPPDATA%\\meridian\\
    """
    if IS_WINDOWS:
        port_file = user_root / "app.port"
        if port_file.exists():
            port = int(port_file.read_text().strip())
            return ServerAddress(tcp_port=port)
        raise FileNotFoundError(f"App port file not found: {port_file}")

    socket_path = user_root / "app.sock"
    if socket_path.exists():
        return ServerAddress(unix_path=socket_path)
    raise FileNotFoundError(f"App socket not found: {socket_path}")
```

### Port Lifecycle

TCP ports are ephemeral resources — unlike Unix domain socket files, they are released when the process exits and can be reused by other processes. The port file serves as the address record:

- **Server startup**: Bind to port 0, write assigned port to file
- **Client connection**: Read port from file, connect
- **Server shutdown**: Port file deleted, port returned to OS pool
- **Stale port file**: If the port file exists but connection fails, the server has crashed — client reports error

This matches the Unix domain socket lifecycle where a stale `.sock` file indicates a crashed server.

### State Path Summary

Two levels of state root:
1. **User state root** (`~/.meridian/` or `%LOCALAPPDATA%\meridian\`) — user-global resources like app server
2. **Project state root** (`~/.meridian/projects/<UUID>/`) — per-project ephemeral state like spawns

The project UUID is read from `.meridian/id` in the repo root. If it doesn't exist, it's generated on first write (lazy initialization).

---

## 5. Process Termination

### Module: `src/meridian/lib/launch/terminate.py` (new or enhance `runner_helpers.py`)

Use `psutil` (already a dependency) for cross-platform process tree termination:

```python
import psutil
from contextlib import suppress

async def terminate_tree(
    process: asyncio.subprocess.Process,
    *,
    grace_secs: float,
) -> None:
    """Cross-platform process tree termination."""
    if process.returncode is not None:
        return
    
    # Snapshot descendants before signaling
    root, children = _snapshot_tree(process.pid)
    if root is None:
        return
    
    # Graceful termination
    for proc in children + [root]:
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            proc.terminate()
    
    _, alive = await asyncio.to_thread(
        psutil.wait_procs, children + [root], timeout=grace_secs
    )
    
    # Force kill survivors
    if alive:
        for proc in alive:
            with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                proc.kill()
```

### Update: Harness Connection Cleanup

Replace per-adapter `process.terminate()/process.kill()` with shared helper:

- `claude_ws.py`: `_terminate_process()` → `terminate_tree()`
- `codex_ws.py`: `_cleanup_resources()` → `terminate_tree()`
- `opencode_http.py`: `_cleanup_runtime()` → `terminate_tree()`

---

## 6. Async Signal Handling

### Module: `src/meridian/lib/launch/shutdown.py` (new or enhance `streaming_runner.py`)

`loop.add_signal_handler()` is not available on Windows default event loop.

**Solution**: Use `signal.signal()` wrapper for both platforms:

```python
import signal
import asyncio

def install_shutdown_handlers(
    shutdown_event: asyncio.Event,
    received_signal: list[signal.Signals | None],
) -> Callable[[], None]:
    """Cross-platform shutdown signal handling."""
    
    def _handler(signum, frame):
        if received_signal[0] is None:
            received_signal[0] = signal.Signals(signum)
        shutdown_event.set()
    
    prev_int = signal.signal(signal.SIGINT, _handler)
    prev_term = signal.signal(signal.SIGTERM, _handler) if IS_POSIX else None
    
    def _restore():
        signal.signal(signal.SIGINT, prev_int)
        if prev_term is not None:
            signal.signal(signal.SIGTERM, prev_term)
    
    return _restore
```

On Windows, `SIGTERM` is not raised by console events. `SIGINT` handles Ctrl+C. For graceful shutdown via other means, use `SetConsoleCtrlHandler` via `win32api` or accept Ctrl+C only.

---

## 7. Harness Storage Resolution

### Module: `src/meridian/lib/platform/storage.py` (new)

```python
from pathlib import Path
import os

def claude_projects_root() -> Path:
    if IS_WINDOWS:
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return appdata / ".claude" / "projects"
    return Path.home() / ".claude" / "projects"

def codex_storage_root() -> Path:
    if IS_WINDOWS:
        localappdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return localappdata / "codex"
    return Path.home() / ".codex"

def opencode_storage_root() -> Path:
    if IS_WINDOWS:
        localappdata = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return localappdata / "opencode"
    return Path.home() / ".local" / "share" / "opencode"
```

### Update: Harness Adapters

- `claude.py`: `_claude_projects_root()` → `storage.claude_projects_root()`
- `codex.py`: hardcoded paths → `storage.codex_storage_root()`
- `opencode.py`: hardcoded paths → `storage.opencode_storage_root()`

---

## 8. Child Environment Shaping

### Module: `src/meridian/lib/launch/env.py` (update)

Add Windows environment variables to allowlist:

```python
_CHILD_ENV_ALLOWLIST = frozenset({
    # Existing Unix vars
    "PATH", "HOME", "USER", "SHELL", "LANG", "TERM", "TMPDIR",
    "PYTHONPATH", "VIRTUAL_ENV",
    # Windows vars
    "USERPROFILE", "HOMEDRIVE", "HOMEPATH",
    "TEMP", "TMP",
    "APPDATA", "LOCALAPPDATA",
    "PATHEXT", "COMSPEC",
    "SYSTEMROOT", "WINDIR",
})
```

### Update: Path Projection

Ensure `MERIDIAN_FS_DIR` and `MERIDIAN_WORK_DIR` use consistent path separators:

```python
def _normalize_meridian_env(env: dict[str, str]) -> None:
    # Existing logic
    # Ensure forward slashes for cross-platform consistency
    for key in ("MERIDIAN_FS_DIR", "MERIDIAN_WORK_DIR"):
        if key in env:
            env[key] = env[key].replace("\\", "/")
```

---

## 9. Symlink Fallback

### Module: `src/meridian/lib/harness/claude_preflight.py` (update)

```python
def ensure_claude_session_accessible(
    source_session_id: str,
    source_cwd: Path | None,
    child_cwd: Path,
) -> None:
    # ... validation ...
    
    target_file = child_project / f"{safe_session_id}.jsonl"
    try:
        os.symlink(source_file, target_file)
    except (FileExistsError, OSError) as exc:
        if isinstance(exc, FileExistsError):
            # Existing logic
            ...
        elif IS_WINDOWS and _is_symlink_privilege_error(exc):
            # Fallback to file copy on Windows without symlink privileges
            import shutil
            try:
                shutil.copy2(source_file, target_file)
            except OSError:
                logger.debug("Claude session bridging failed, proceeding without")
        else:
            logger.debug("Symlink creation failed", exc_info=True)

def _is_symlink_privilege_error(exc: OSError) -> bool:
    # Windows error 1314: "A required privilege is not held by the client"
    return IS_WINDOWS and getattr(exc, 'winerror', None) == 1314
```

---

## 10. Guardrail Script Execution

### Module: `src/meridian/lib/safety/guardrails.py` (update)

```python
def _resolve_guardrail_command(script: Path) -> list[str]:
    if IS_WINDOWS:
        suffix = script.suffix.lower()
        if suffix in {".bat", ".cmd"}:
            return ["cmd.exe", "/c", str(script)]
        elif suffix == ".ps1":
            return ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(script)]
        elif suffix in {".exe", ".com"}:
            return [str(script)]
        else:
            # Try direct execution, fallback to cmd
            return [str(script)]
    else:
        # Existing Unix logic
        if not os.access(script, os.X_OK):
            return ["bash", str(script)]
        return [str(script)]
```

---

## 11. Command Parsing

### Module: `src/meridian/lib/launch/context.py` (update)

`shlex.split()` uses POSIX quoting by default. On Windows, use `posix=False`:

```python
def _parse_harness_command(override: str) -> list[str]:
    import shlex
    if IS_WINDOWS:
        # Windows cmd.exe quoting (not POSIX)
        # shlex doesn't fully support cmd.exe semantics, but posix=False is closer
        return shlex.split(override, posix=False)
    return shlex.split(override)
```

---

## Dependency Changes

### MVP Dependencies

No new dependencies required for MVP. Existing dependencies (`psutil`) already support Windows.

```toml
[project]
dependencies = [
    # psutil already present, works on Windows
    "psutil>=5.9.0",
]
```

### Follow-up Dependencies (CLI Terminal Support)

```toml
[project.optional-dependencies]
windows-terminal = [
    "pywinpty>=2.0.0",
]
```

**Note**: `pywinpty` is only needed for CLI primary launch with PTY semantics. Web UI spawns and pipe-based execution work without it.

---

## File Change Summary

### MVP Changes

| File | Change Type | Description |
|------|-------------|-------------|
| `src/meridian/lib/platform/__init__.py` | New | Platform detection constants (`IS_WINDOWS`, `IS_POSIX`) |
| `src/meridian/lib/platform/locking.py` | New | Cross-platform file locking (`lock_file()` context manager) |
| `src/meridian/lib/platform/ipc.py` | New | IPC address resolution (`ServerAddress`, `resolve_control_address()`, `resolve_app_address()`) |
| `src/meridian/lib/platform/storage.py` | New | Harness storage path resolution |
| `src/meridian/lib/launch/terminate.py` | New | Process tree termination via psutil |
| `src/meridian/lib/state/atomic.py` | Update | Skip directory fsync on Windows |
| `src/meridian/lib/state/event_store.py` | Update | Use platform locking |
| `src/meridian/lib/state/session_store.py` | Update | Use platform locking |
| `src/meridian/lib/streaming/control_socket.py` | Update | Platform dispatch for server startup (Unix socket vs TCP localhost) |
| `src/meridian/lib/streaming/signal_canceller.py` | Update | Use `resolve_app_address()` for cross-process cancel |
| `src/meridian/cli/app_cmd.py` | Update | Platform dispatch for server binding, port file write on Windows |
| `src/meridian/lib/harness/claude.py` | Update | Platform storage |
| `src/meridian/lib/harness/codex.py` | Update | Platform storage |
| `src/meridian/lib/harness/opencode.py` | Update | Platform storage |
| `src/meridian/lib/harness/claude_preflight.py` | Update | Symlink fallback |
| `src/meridian/lib/launch/env.py` | Update | Windows env vars |
| `src/meridian/lib/launch/context.py` | Update | Windows command parsing |
| `src/meridian/lib/safety/guardrails.py` | Update | Windows script execution |
| `src/meridian/lib/launch/streaming_runner.py` | Update | Platform signal handling |
| `src/meridian/lib/harness/connections/*.py` | Update | Use `terminate_tree()` |

### Follow-up Changes (CLI Terminal Support)

| File | Change Type | Description |
|------|-------------|-------------|
| `src/meridian/lib/launch/terminal/` | New dir | Interactive transport abstraction |
| `src/meridian/lib/launch/process.py` | Refactor | Extract terminal transport |

---

## Testing Strategy

### MVP Tests

1. **Import tests**: Verify clean import on Windows without Unix modules
2. **Locking tests**: Concurrent write tests on Windows via `msvcrt.locking()`
3. **IPC tests**: TCP localhost control socket and app server on Windows
   - Port file creation and reading
   - Cross-process cancel via HTTP
   - Stale port file detection (server crashed)
4. **Atomic write tests**: Verify `os.replace()` atomicity, skip directory fsync
5. **Termination tests**: Process tree cleanup on Windows via psutil
6. **Smoke tests**: Full spawn lifecycle on Windows (pipe-based, via web UI)

### Follow-up Tests (CLI Terminal Support)

7. **Terminal transport tests**: ConPTY allocation and resize on Windows via `pywinpty`

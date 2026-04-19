# Windows Runtime Compatibility Design

Small, focused changes to make meridian fully runnable on Windows.

## Platform Detection

Use existing `IS_WINDOWS` constant from `meridian.lib.platform`:

```python
from meridian.lib.platform import IS_WINDOWS
```

This constant already exists and is used throughout the codebase. No new detection mechanism needed.

## 1. PTY Skip on Windows (process.py)

### Behavior

On Windows, `_run_primary_process_with_capture()` always uses the subprocess.Popen passthrough branch, never the PTY+fork branch.

### Interface Decision

Guard the PTY branch with platform check. The simplest approach: force `output_log_path = None` on Windows before the conditional, which naturally routes to the existing passthrough branch.

```python
# Line ~167 in _run_primary_process_with_capture()
def _run_primary_process_with_capture(
    *,
    command: tuple[str, ...],
    cwd: Path,
    env: dict[str, str],
    output_log_path: Path | None,
    on_child_started: Callable[[int], None] | None = None,
) -> tuple[int, int | None]:
    from meridian.lib.platform import IS_WINDOWS
    
    # Windows cannot use PTY — force passthrough branch
    if IS_WINDOWS:
        output_log_path = None
    
    if output_log_path is None or not sys.stdin.isatty() or not sys.stdout.isatty():
        # existing subprocess.Popen passthrough
        ...
```

### Tradeoff

Windows foreground spawns lose `output.jsonl` capture. This is acceptable per requirements — harness session logs still exist and provide the same operational visibility.

## 2. TCP Localhost for App Server (app_cmd.py)

### Behavior

On Windows, use TCP `127.0.0.1:port` instead of Unix Domain Socket.

### Interface Decision

Add optional `--port` CLI argument. When `--port` is specified OR platform is Windows, use TCP binding instead of UDS.

| Platform | Flag | Binding |
|----------|------|---------|
| POSIX | (none) | UDS `app.sock` |
| POSIX | `--port 8420` | TCP `127.0.0.1:8420` |
| Windows | (none) | TCP `127.0.0.1:8420` (default) |
| Windows | `--port N` | TCP `127.0.0.1:N` |

Default TCP port: **8420** (memorable, unlikely to conflict).

### Implementation Shape

```python
def run_app(
    uds: str | None = None,
    port: int | None = None,  # NEW
    proxy: str | None = None,
    debug: bool = False,
    allow_unsafe_no_permissions: bool = False,
) -> None:
    from meridian.lib.platform import IS_WINDOWS
    
    # ...setup...
    
    use_tcp = IS_WINDOWS or port is not None
    if use_tcp:
        resolved_port = port or 8420
        print(f"Starting meridian app on http://127.0.0.1:{resolved_port}")
        uvicorn_module.run(app, host="127.0.0.1", port=resolved_port, log_level="info")
    else:
        socket_path = (uds or "").strip() or str(state_root / "app.sock")
        # ...existing UDS logic...
```

### Discovery

Clients that need to connect to the app server (e.g., `signal_canceller.py`) will need to:
1. Check for TCP mode via port file OR fall back to UDS
2. Write `.meridian/app.port` when using TCP binding
3. Read port file before attempting UDS connection

Port file format: single line containing port number as text.

## 3. TCP Localhost for Control Socket (control_socket.py)

### Behavior

On Windows, use `asyncio.start_server(host='127.0.0.1', port=0)` instead of `asyncio.start_unix_server()`.

### Interface Decision

Platform-conditional in `ControlSocketServer.start()`. Use dynamic port allocation (`port=0`) and write assigned port to discovery file.

| Platform | Socket | Discovery |
|----------|--------|-----------|
| POSIX | `control.sock` | Path existence |
| Windows | `127.0.0.1:N` | `control.port` file |

### Implementation Shape

```python
class ControlSocketServer:
    def __init__(self, spawn_id: SpawnId, socket_path: Path, manager: SpawnManager):
        self._spawn_id = spawn_id
        self._socket_path = socket_path  # On Windows, repurposed as parent dir
        self._port_file = socket_path.with_suffix('.port')  # control.port
        self._manager = manager
        self._server: asyncio.AbstractServer | None = None
        self._port: int | None = None  # Assigned TCP port on Windows

    async def start(self) -> None:
        from meridian.lib.platform import IS_WINDOWS
        
        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        
        if IS_WINDOWS:
            self._server = await asyncio.start_server(
                self._handle_client, host='127.0.0.1', port=0
            )
            # Extract assigned port and write to discovery file
            addr = self._server.sockets[0].getsockname()
            self._port = addr[1]
            self._port_file.write_text(str(self._port))
        else:
            self._socket_path.unlink(missing_ok=True)
            self._server = await asyncio.start_unix_server(
                self._handle_client, path=str(self._socket_path)
            )

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        # Cleanup discovery artifacts
        from meridian.lib.platform import IS_WINDOWS
        if IS_WINDOWS:
            self._port_file.unlink(missing_ok=True)
        else:
            self._socket_path.unlink(missing_ok=True)
```

### Client Updates

Any code that connects to a control socket (currently just internal use via spawn_manager) needs platform-aware connection:

```python
from meridian.lib.platform import IS_WINDOWS

if IS_WINDOWS:
    port = int(port_file.read_text().strip())
    reader, writer = await asyncio.open_connection('127.0.0.1', port)
else:
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
```

## 4. Signal Canceller Updates (signal_canceller.py)

The `_cancel_app_spawn_over_http()` method uses `aiohttp.UnixConnector`. On Windows, switch to standard TCP:

```python
async def _cancel_app_spawn_over_http(self, spawn_id: SpawnId) -> CancelOutcome:
    from meridian.lib.platform import IS_WINDOWS
    
    aiohttp = import_module("aiohttp")
    timeout = cast("object", aiohttp.ClientTimeout(total=10.0))
    
    if IS_WINDOWS:
        port_file = self._state_root / "app.port"
        if not port_file.exists():
            raise RuntimeError(f"app port file not found: {port_file}")
        port = int(port_file.read_text().strip())
        connector = None  # Use default TCP connector
        url = f"http://127.0.0.1:{port}/api/spawns/{spawn_id}/cancel"
    else:
        socket_path = self._state_root / "app.sock"
        if not socket_path.exists():
            raise RuntimeError(f"app socket not found: {socket_path}")
        connector = cast("object", aiohttp.UnixConnector(path=str(socket_path)))
        url = f"http://localhost/api/spawns/{spawn_id}/cancel"
    
    # ...rest of method with connector handling...
```

## File Summary

| File | Change |
|------|--------|
| `lib/launch/process.py` | Add Windows guard to skip PTY branch |
| `cli/app_cmd.py` | Add `--port` arg, TCP fallback, write `app.port` |
| `lib/streaming/control_socket.py` | Platform-conditional socket creation, `control.port` discovery |
| `lib/streaming/signal_canceller.py` | Platform-conditional connector for app server |

## Testing Strategy

1. **Existing tests pass on POSIX** — no behavioral change on Unix/Mac
2. **Windows CI smoke test** — verify `meridian spawn`, `meridian app`, and control socket work
3. **Port file lifecycle** — port files created on start, removed on stop

## Open Questions

None — scope is well-defined and approach follows existing patterns.

## Decision Log

| Decision | Rationale |
|----------|-----------|
| Use existing `IS_WINDOWS` | Pattern already established; no new abstraction needed |
| Dynamic port (port=0) for control socket | Multiple spawns need multiple sockets; fixed port would conflict |
| Fixed default port (8420) for app server | Single app server per state root; predictable for tooling |
| Port file discovery | Filesystem discovery mirrors UDS pattern; no config plumbing needed |
| TCP fallback Windows-only (default) | Minimizes POSIX behavioral change; `--port` opt-in for cross-platform TCP |

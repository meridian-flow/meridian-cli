# Phase 1: Windows Runtime Fallbacks

## Scope

Implement platform-conditional paths for PTY, app server, control socket, and signal canceller to enable Windows runtime.

## EARS Claims

- **WIN-01**: When platform is Windows, the system SHALL skip PTY branch and use subprocess.Popen passthrough
- **WIN-02**: When platform is Windows OR `--port` is specified, the app server SHALL bind to TCP localhost instead of Unix socket
- **WIN-03**: When platform is Windows, the control socket SHALL use TCP with dynamic port allocation and write `control.port` for discovery
- **WIN-04**: When platform is Windows, signal canceller SHALL use TCP connector with port file discovery instead of Unix socket

## Files Modified

### 1. `src/meridian/lib/launch/process.py`

**Location**: `_run_primary_process_with_capture()` function, ~line 159

**Change**: Add Windows guard at function entry to force `output_log_path = None`, routing to existing subprocess.Popen branch.

```python
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
        # existing subprocess.Popen passthrough...
```

### 2. `src/meridian/cli/main.py`

**Location**: `app_command()` function, ~line 504

**Change**: Add `--port` CLI parameter and pass to `run_app()`.

```python
@app.command(name="app")
def app_command(
    uds: Annotated[...] = None,
    port: Annotated[
        int | None,
        Parameter(
            name="--port",
            help="TCP port for the app server (default on Windows: 8420). Enables TCP binding instead of Unix socket.",
        ),
    ] = None,
    proxy: Annotated[...] = None,
    ...
) -> None:
    run_app(
        uds=uds,
        port=port,
        proxy=proxy,
        ...
    )
```

### 3. `src/meridian/cli/app_cmd.py`

**Change**: 
- Add `port: int | None = None` parameter
- Add platform-conditional TCP/UDS binding
- Write `app.port` file when using TCP

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
        port_file = state_root / "app.port"
        port_file.write_text(str(resolved_port))
        print(f"Starting meridian app on http://127.0.0.1:{resolved_port}")
        uvicorn_module.run(app, host="127.0.0.1", port=resolved_port, log_level="info")
    else:
        # existing UDS logic...
```

### 4. `src/meridian/lib/streaming/control_socket.py`

**Change**:
- Add `_port_file` and `_port` instance variables
- Platform-conditional `start()` using `asyncio.start_server()` vs `asyncio.start_unix_server()`
- Write `control.port` on Windows
- Platform-conditional cleanup in `stop()`

```python
class ControlSocketServer:
    def __init__(self, spawn_id: SpawnId, socket_path: Path, manager: SpawnManager):
        self._spawn_id = spawn_id
        self._socket_path = socket_path
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
        from meridian.lib.platform import IS_WINDOWS
        if IS_WINDOWS:
            self._port_file.unlink(missing_ok=True)
        else:
            self._socket_path.unlink(missing_ok=True)
```

### 5. `src/meridian/lib/streaming/signal_canceller.py`

**Location**: `_cancel_app_spawn_over_http()` method, ~line 139

**Change**: Platform-conditional connector:
- Windows: read `app.port`, use standard TCP connector
- POSIX: existing Unix socket connector

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
    
    # Use connector in session...
```

## Dependencies

None — all changes are leaf-level.

## Tester Lanes

- **@verifier**: `pytest`, `pyright`, `ruff` pass
- **@smoke-tester**: Verify `meridian app --port 8420` binds to TCP, `--port` flag accessible from CLI

## Exit Criteria

1. All existing tests pass
2. `--port` flag appears in `meridian app --help`
3. `IS_WINDOWS` guards present in all 5 files
4. Port file write/read logic implemented for TCP discovery

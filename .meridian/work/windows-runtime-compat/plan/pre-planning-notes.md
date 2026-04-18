# Pre-Planning Notes

## Code Observations

1. **IS_WINDOWS constant**: Already exists at `meridian.lib.platform.IS_WINDOWS`, used in 5+ files. Pattern established.

2. **process.py structure**: PTY branch starts at line 190 (`import pty`). The subprocess.Popen branch at line 167-188 already handles non-TTY cases correctly. Routing Windows to this branch is safe.

3. **app_cmd.py structure**: Current function signature is `run_app(uds, proxy, debug, allow_unsafe_no_permissions)`. Adding `port` parameter is straightforward.

4. **main.py CLI definition**: Uses Griffe `Annotated[type, Parameter(...)]` pattern. Adding `--port` follows existing `--uds` pattern exactly.

5. **control_socket.py**: Uses `asyncio.start_unix_server()`. The `asyncio.start_server()` equivalent for TCP is identical API shape — just different function name and kwargs.

6. **signal_canceller.py**: Uses `aiohttp.UnixConnector`. Standard `aiohttp.ClientSession` without connector uses TCP by default — simpler path on Windows.

## Design Validation

- Design decisions doc already captures key tradeoffs
- No feasibility probes needed — all APIs are standard library/well-documented
- Port 8420 default is arbitrary but memorable; no conflict analysis needed for this scope

## Edge Cases

1. **Both `--uds` and `--port` specified**: The design prioritizes `--port` (TCP mode) when specified, regardless of `--uds`. Explicit TCP trumps UDS path.

2. **Port file cleanup on crash**: Port file may be stale if app crashes. Not a safety issue — next start overwrites. Same as UDS socket stale file handling.

3. **Dynamic port race**: Control socket uses port=0 with immediate write to port file. Brief race window between port allocation and file write is acceptable — client retries handle this.

## Constraints

- Cannot test Windows code path on POSIX CI — only structural verification (guards present, code paths exist)
- Windows CI job required for end-to-end verification (out of scope for this plan)

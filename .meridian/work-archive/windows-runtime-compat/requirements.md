# Windows Runtime Compatibility

Make meridian fully runnable on Windows (not just importable).

## Scope

### Simplified Approach

Rather than full PTY/ConPTY parity, use cross-platform fallbacks:

1. **Skip PTY on Windows** — Foreground spawns use `subprocess.Popen` passthrough (no output capture). The harness runs and outputs directly to the terminal; meridian doesn't capture `output.jsonl` for interactive Windows sessions. Harness session logs still exist.

2. **TCP localhost for IPC** — Instead of Unix sockets or named pipes, use `asyncio.start_server(host='127.0.0.1', port=...)` and uvicorn TCP binding. Cross-platform out of the box.

### Changes Required

| Area | Current (POSIX) | Windows Target |
|------|-----------------|----------------|
| Foreground spawn | PTY + fork + capture | subprocess.Popen passthrough |
| App server | Unix socket (`app.sock`) | TCP localhost |
| Control socket | `asyncio.start_unix_server()` | `asyncio.start_server()` TCP |

### Code Locations

- `src/meridian/lib/launch/process.py:167` — PTY branch; add Windows guard to skip
- `src/meridian/cli/app_cmd.py:32` — uvicorn UDS; add TCP fallback
- `src/meridian/lib/streaming/control_socket.py:27` — Unix server; add TCP fallback

## Tradeoffs

| What you lose | Impact |
|---------------|--------|
| `output.jsonl` capture on Windows foreground spawns | Low — harness session logs exist |
| Filesystem-path-based IPC | Low — TCP localhost is standard |

| What you gain | Impact |
|---------------|--------|
| No ConPTY/winpty complexity | High — removes most complex Windows work |
| No named pipes | Medium — stays with cross-platform asyncio |
| Smaller test surface | Medium — no platform-specific IPC code paths |

## Dependencies

- `windows-compat-primitives` (done) — deferred imports, cross-platform locking, psutil termination

## Acceptance Criteria

1. `meridian spawn` works on Windows (foreground = subprocess passthrough, no capture)
2. `meridian app` works on Windows (TCP localhost)
3. Control socket IPC works on Windows (TCP localhost)
4. All existing tests pass on both platforms

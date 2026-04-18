# Windows Runtime Compatibility Decisions

## Platform Detection: Reuse `IS_WINDOWS`

**Decision**: Use existing `meridian.lib.platform.IS_WINDOWS` constant.

**Alternatives considered**:
- New module-level constant per file: Rejected — duplicates existing pattern
- Runtime `sys.platform` checks inline: Rejected — constant is cleaner

**Rationale**: The project already has this constant and uses it throughout. Adding new detection would fragment the pattern.

## PTY Skip: Force `output_log_path = None` on Windows

**Decision**: Set `output_log_path = None` before the branch check, naturally routing Windows to the subprocess.Popen passthrough.

**Alternatives considered**:
- Separate conditional branch for Windows: More explicit but duplicates passthrough logic
- Try/except around PTY imports: Less readable

**Rationale**: The existing passthrough branch already handles non-TTY cases correctly. Reusing it minimizes code paths and risk.

## TCP Port for App Server: Fixed default 8420, `--port` opt-in

**Decision**: Default to port 8420 on Windows; allow `--port` override on any platform.

**Alternatives considered**:
- Dynamic port (port=0): Requires discovery mechanism for external tools
- User-configured via env var: More ceremony for uncommon case

**Rationale**: Single app server per state root means port collision is unlikely. Fixed port is predictable for browser bookmarks and tooling.

## TCP Port for Control Socket: Dynamic with Port File

**Decision**: Use `port=0` for OS allocation, write assigned port to `control.port` file.

**Alternatives considered**:
- Fixed port per spawn: Would require port allocation/tracking
- Port embedded in spawn record: State store mutation at IPC layer is wrong abstraction

**Rationale**: Multiple active spawns need multiple sockets. Dynamic allocation with filesystem discovery mirrors the UDS pattern (socket file existence = endpoint available).

## TCP Fallback Scope: Windows-only by Default

**Decision**: TCP is the Windows default; POSIX continues using UDS. `--port` flag enables TCP on any platform.

**Alternatives considered**:
- TCP everywhere: Simpler code but loses UDS security/perf benefits on POSIX
- Config-driven fallback: Overengineered for this scope

**Rationale**: UDS works well on POSIX and is marginally more secure (filesystem permissions). No reason to change working behavior.

## 2026-04-18: Phase 1 Implementation

### app.port directory creation fix
During smoke testing, discovered that `app.port` write failed when state_root directory didn't exist. Added `port_file.parent.mkdir(parents=True, exist_ok=True)` before write, consistent with UDS path pattern.

### State root location
Smoke test expected `app.port` at `$MERIDIAN_STATE_ROOT/app.port`, but runtime state follows existing `resolve_state_root()` pattern which returns user-level project state directory. This is correct and consistent with existing app state management.

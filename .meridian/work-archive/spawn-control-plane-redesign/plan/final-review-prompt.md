# Final Review: Spawn Control Plane Redesign

Review the complete spawn control plane redesign implementation across all 6 phases.

## Commits to Review

The implementation spans 4 commits on `main`:
1. Phase 1: Foundation primitives (heartbeat, inject lock, LaunchMode)
2. Round 2: Transport+Auth, Interrupt classifier, Liveness
3. Phase 5: Cancel core (SignalCanceller, two-lane dispatch)
4. Phase 6: HTTP surface convergence

## Key Files

### New files
- `src/meridian/lib/streaming/heartbeat.py` — shared heartbeat primitive
- `src/meridian/lib/streaming/inject_lock.py` — per-spawn asyncio lock
- `src/meridian/lib/streaming/signal_canceller.py` — two-lane cancel dispatcher
- `src/meridian/lib/ops/spawn/authorization.py` — ancestry-based auth guard

### Modified files
- `src/meridian/lib/app/server.py` — AF_UNIX, cancel endpoint, inject parity
- `src/meridian/lib/streaming/spawn_manager.py` — heartbeat, inject serialization
- `src/meridian/lib/streaming/control_socket.py` — cancel rejection, auth
- `src/meridian/lib/launch/streaming_runner.py` — classifier fix, heartbeat
- `src/meridian/cli/app_cmd.py` — AF_UNIX transport
- `src/meridian/cli/spawn.py` — cancel wiring
- `src/meridian/lib/state/spawn_store.py` — LaunchMode extension

## Design Alignment

Review against the design package at `$MERIDIAN_WORK_DIR/design/`. Key decisions to verify:
- D-03: Two-lane cancel (SIGTERM for CLI, in-process for app)
- D-13: No SIGKILL
- D-14: depth>0 missing caller → deny
- D-17: 400/422 validation split
- D-18: Control socket ack ordering, HTTP uses inbound_seq
- D-19: Peercred failure → DENY

## What to Look For

1. **Race conditions** — cancel/finalizing TOCTOU, concurrent inject ordering
2. **Cross-phase drift** — do phases 2-6 build correctly on phase 1's primitives?
3. **Authorization gaps** — is every lifecycle surface gated? Is inject ungated per spec?
4. **Error contract** — do HTTP status codes match the spec table?
5. **Structural debt** — any dead code from removed surfaces? Missing cleanup?

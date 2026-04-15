# Leaf Ownership Ledger — orphan-run reaper fix (Round 2)

| EARS ID | Owning phase | Status | Tester lane | Evidence pointer | Notes |
|---|---|---|---|---|---|
| `S-LC-001` | `Phase 2` | `pending` |  |  |  |
| `S-LC-002` | `Phase 2` | `pending` |  |  |  |
| `S-LC-003` | `Phase 2` | `pending` |  |  |  |
| `S-LC-004` | `Phase 5` | `pending` |  |  | `revised: Round 2 requires flock-scoped CAS for running -> finalizing` |
| `S-LC-005` | `Phase 5` | `pending` |  |  |  |
| `S-LC-006` | `Phase 5` | `pending` |  |  | `revised: CAS miss is non-fatal; authority resolves later` |
| `S-RN-001` | `Phase 5` | `pending` |  |  | `revised: heartbeat reset is tied to the explicit finalizing handoff` |
| `S-RN-002` | `Phase 4` | `pending` |  |  | `revised: origin is now mandatory data on finalize events` |
| `S-RN-003` | `Phase 4` | `pending` |  |  |  |
| `S-RN-004` | `Phase 1` | `pending` |  |  | `revised: runner-owned periodic heartbeat replaces harness-output cadence assumptions` |
| `S-RN-005` | `Phase 4` | `pending` |  |  | `revised: full 11-writer mapping is contractual` |
| `S-RN-006` | `Phase 1` | `pending` |  |  | `revised: outer finally owns heartbeat shutdown discipline` |
| `S-RP-001` | `Phase 1` | `pending` |  |  | `revised: recent activity gate keys off heartbeat plus artifact mtimes` |
| `S-RP-002` | `Phase 5` | `pending` |  |  |  |
| `S-RP-003` | `Phase 5` | `pending` |  |  |  |
| `S-RP-004` | `Phase 4` | `pending` |  |  | `revised: reconciler success writes carry explicit origin` |
| `S-RP-005` | `Phase 4` | `pending` |  |  |  |
| `S-RP-006` | `Phase 1` | `pending` |  |  | `revised: depth gate lives inside reconcile_active_spawn, not only batch fan-in` |
| `S-RP-007` | `Phase 1` | `pending` |  |  |  |
| `S-RP-008` | `Phase 5` | `pending` |  |  | `new: reconciler finalize must re-validate under the flock` |
| `S-RP-009` | `Phase 1` | `pending` |  |  | `new: reconcile_active_spawn splits into pure decider plus I/O shell` |
| `S-PR-001` | `Phase 4` | `pending` |  |  | `revised: authority keys off origin / terminal_origin, not error strings` |
| `S-PR-002` | `Phase 4` | `pending` |  |  |  |
| `S-PR-003` | `Phase 4` | `pending` |  |  | `revised: legacy-only shim; no new writer may omit origin` |
| `S-PR-004` | `Phase 4` | `pending` |  |  |  |
| `S-PR-005` | `Phase 4` | `pending` |  |  | `new: derived terminal_origin on SpawnRecord` |
| `S-PR-006` | `Phase 5` | `pending` |  |  | `new: late status updates never downgrade a terminal row` |
| `S-CF-001` | `Phase 3` | `pending` |  |  |  |
| `S-CF-002` | `Phase 3` | `pending` |  |  |  |
| `S-CF-003` | `Phase 4` | `pending` |  |  |  |
| `S-CF-004` | `Phase 3` | `pending` |  |  | `revised: models render literal finalizing instead of exited_at heuristics` |
| `S-OB-001` | `Phase 3` | `pending` |  |  |  |
| `S-OB-002` | `Phase 1` | `pending` |  |  |  |
| `S-OB-003` | `Phase 5` | `pending` |  |  | `new: log reconciler CAS-miss drops explicitly` |
| `S-BF-001` | `Phase 4` | `pending` |  |  |  |
| `S-BF-002` | `Phase 4` | `pending` |  |  |  |

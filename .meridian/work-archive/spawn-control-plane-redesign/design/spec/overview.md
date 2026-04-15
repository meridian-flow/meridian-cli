# Spec Overview — Spawn Control Plane (v2r2)

The behavioral contract for the spawn control plane after the #28-#31
redesign. EARS leaves are organized by surface area; each leaf is
independently verifiable. The `architecture/` tree explains how the
implementation realizes each leaf; `refactors.md` lists the structural
rearrangements that sequence the work.

## Subsystems

| Subsystem | File | Coverage |
|---|---|---|
| Cancel (signal-based, lifecycle) | `spec/cancel.md` | #29, #30 lifecycle parity, timeout kills |
| Interrupt (non-fatal, intra-turn) | `spec/interrupt.md` | #28, resumption contract |
| Inject (text, intra-turn) | `spec/inject.md` | #31 ordering, HTTP parity for text |
| Reaper liveness (one contract) | `spec/liveness.md` | #30, app-managed parity |
| HTTP surface parity | `spec/http_surface.md` | #31 parity for cancel/interrupt |
| Authorization for lifecycle ops | `spec/authorization.md` | new constraint scope |

## Leaf-ID convention

`<SUBSYSTEM>-<3-digit>` — e.g., `CAN-001`, `INT-001`, `INJ-001`,
`LIV-001`, `HTTP-001`, `AUTH-001`. Reserved ranges per subsystem allow
inserts without renumbering.

## v2r2 changes from v2

- Cancel adopts explicit two-lane dispatch: SIGTERM for CLI spawns,
  in-process for app spawns (D-03 revised, resolves BL-1 accurately).
- SIGKILL removed entirely from cancel pipeline (D-13, resolves TOCTOU).
- HTTP validation split: schema → 422, semantic → 400 (D-17).
- INJ-002 ack ordering narrowed: control socket guaranteed, HTTP uses
  `inbound_seq` (D-18).
- Peercred failure → DENY for lifecycle ops (D-19, resolves macOS
  fallback and peer-exit race).

## v2 changes from v1

- `finalizing` status is a hard no-escalation gate in `SignalCanceller`
  (CAN-008, resolves BL-4).
- Terminal-cancel HTTP returns `409` consistently (CAN-007, resolves BL-7).
- Authorization transport moves to AF_UNIX `SO_PEERCRED` (AUTH-001..006,
  resolves BL-3 + BL-6).
- `depth > 0` with missing caller is deny-by-default (AUTH-007, resolves
  env-drop major).
- All feasibility items closed before any leaf depends on them.
- Verification plan includes fault-injection probes per success criterion.

## Out-of-scope statements

- Reaper internals (decide/IO split, authority rule, heartbeat window)
  stay as-is unless a leaf forces a change. Existing reaper EARS
  statements from the orphan-run-reaper-fix design remain authoritative.
- The `meridian streaming serve` developer-only surface is not its own
  subsystem — it is one observation point for the spec leaves below.

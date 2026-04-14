# Spec Overview — Spawn Control Plane

The behavioral contract for the spawn control plane after the #28-#31 redesign.
EARS leaves are organized by surface area; each leaf is independently
verifiable. The `architecture/` tree explains how the implementation realizes
each leaf; the `refactors.md` agenda lists the structural rearrangements that
sequence the work.

## Subsystems

| Subsystem | File | Coverage |
|---|---|---|
| Cancel (signal-based, lifecycle) | `spec/cancel.md` | #29, #30 lifecycle parity, timeout-driven kills |
| Interrupt (non-fatal, intra-turn) | `spec/interrupt.md` | #28, resumption contract |
| Inject (text, intra-turn) | `spec/inject.md` | #31 ordering, #31 HTTP parity for text |
| Reaper liveness contract (one contract) | `spec/liveness.md` | #30, app-managed parity |
| HTTP surface parity | `spec/http_surface.md` | #31 parity for cancel/interrupt |
| Authorization for lifecycle ops | `spec/authorization.md` | new constraint scope |

## Leaf-ID convention

`<SUBSYSTEM>-<3-digit>` — e.g., `CAN-001`, `INT-001`, `INJ-001`, `LIV-001`,
`HTTP-001`, `AUTH-001`. Reserved ranges per subsystem allow inserts without
renumbering. Each leaf states the trigger, the required system response, and
the observable that proves the response.

## Out-of-scope statements

- Reaper internals (decide/IO split, authority rule, heartbeat window) stay
  as-is unless a leaf forces a change. Existing reaper EARS statements from
  the orphan-run-reaper-fix design remain authoritative for the parts they
  cover.
- The `meridian streaming serve` developer-only surface is not its own
  subsystem — it is one observation point for the spec leaves below.

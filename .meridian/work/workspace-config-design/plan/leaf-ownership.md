# Leaf Ownership

Remaining-scope leaf ownership for the regenerated plan. Every row is exclusive;
later phases may regression-test earlier leaves, but the owner phase below is
the phase responsible for closing the contract.

| Leaf ID | Owner phase | Status | Tester lane | Evidence pointer | Notes |
|---|---|---|---|---|---|
| `WS-1.u1` | `phase-2-workspace-model-and-inspection` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | — |
| `WS-1.u2` | `phase-2-workspace-model-and-inspection` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | — |
| `WS-1.u3` | `phase-2-workspace-model-and-inspection` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | — |
| `WS-1.u4` | `phase-2-workspace-model-and-inspection` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | — |
| `WS-1.s1` | `phase-2-workspace-model-and-inspection` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | Depends on the shared surfacing builder for quiet `workspace.status = none` inspection output. |
| `WS-1.e1` | `phase-2-workspace-model-and-inspection` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | — |
| `WS-1.e2` | `phase-2-workspace-model-and-inspection` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | Depends on the shared surfacing builder for unknown-key warnings in `config show` and `doctor`. |
| `WS-1.c1` | `phase-2-workspace-model-and-inspection` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | Depends on the shared surfacing builder for `status = invalid` inspection output while this phase also adds pre-launch command gating. |
| `CTX-1.u1` | `phase-3-launch-projection-and-applicability` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | — |
| `CTX-1.u2` | `phase-3-launch-projection-and-applicability` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | — |
| `CTX-1.e1` | `phase-3-launch-projection-and-applicability` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | — |
| `CTX-1.w1` | `phase-3-launch-projection-and-applicability` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | — |
| `CTX-1.w2` | `phase-3-launch-projection-and-applicability` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | — |
| `SURF-1.u1` | `phase-2-workspace-model-and-inspection` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | Depends on the shared surfacing builder introduced in phase 1. |
| `SURF-1.e1` | `phase-2-workspace-model-and-inspection` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | Depends on the shared surfacing builder introduced in phase 1. |
| `SURF-1.e2` | `phase-2-workspace-model-and-inspection` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | Depends on the shared surfacing builder introduced in phase 1. |
| `SURF-1.e3` | `phase-3-launch-projection-and-applicability` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | — |
| `SURF-1.e4` | `phase-3-launch-projection-and-applicability` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | Uses the phase-1 surface vocabulary and phase-2 workspace snapshot to make applicability downgrades explicit. |
| `BOOT-1.u1` | `phase-1-config-surface-convergence` | `verified` | `@verifier + @unit-tester + @smoke-tester` | `.meridian/spawns/p2090/report.md` | Runtime-only bootstrap preserved; shared inspection seam closed. |
| `BOOT-1.e1` | `phase-1-config-surface-convergence` | `verified` | `@verifier + @unit-tester + @smoke-tester` | `.meridian/spawns/p2090/report.md` | `config init` convergence proven; no-Mars-side-effect proof via targeted test. |
| `BOOT-1.e2` | `phase-2-workspace-model-and-inspection` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | — |

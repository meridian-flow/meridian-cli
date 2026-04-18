# Leaf Ownership

Active-scope leaf ownership for the simplified UUID plan. The old
workspace-topology leaves (`WS-1.*`, `CTX-1.*`, `SURF-1.*`, `BOOT-1.e2`) belong
to the superseded plan and are intentionally absent from this ledger. Every row
below is exclusive; later phases may regression-test earlier leaves, but the
owner phase is responsible for closing the contract.

| Leaf ID | Owner phase | Status | Tester lane | Evidence pointer | Notes |
|---|---|---|---|---|---|
| `CFG-1.u1` | `phase-1-config-surface-convergence` | `verified` | `@verifier + @unit-tester + @smoke-tester` | `.meridian/spawns/p2090/report.md` | Preserved completed phase; later phases regression-test that runtime-home changes do not move project config into user state. |
| `CFG-1.u2` | `phase-1-config-surface-convergence` | `verified` | `@verifier + @unit-tester + @smoke-tester` | `.meridian/spawns/p2090/report.md` | Later phases must preserve field-by-field precedence while changing only runtime-state paths. |
| `CFG-1.u3` | `phase-1-config-surface-convergence` | `verified` | `@verifier + @unit-tester + @smoke-tester` | `.meridian/spawns/p2090/report.md` | Project settings stay in `meridian.toml`; no workspace-topology surface is revived. |
| `BOOT-1.u1` | `phase-1-config-surface-convergence` | `verified` | `@verifier + @unit-tester + @smoke-tester` | `.meridian/spawns/p2090/report.md` | Generic startup bootstrap policy remains the preserved baseline. |
| `BOOT-1.e1` | `phase-1-config-surface-convergence` | `verified` | `@verifier + @unit-tester + @smoke-tester` | `.meridian/spawns/p2090/report.md` | `config init` remains the only creator of `meridian.toml`. |
| `HOME-1.u1` | `phase-2-uuid-and-user-state-foundation` | `pending` | `@verifier + @unit-tester` | `TBD` | `MERIDIAN_HOME` precedence and default user-root resolution are helper-level foundation work. |
| `HOME-1.u2` | `phase-2-uuid-and-user-state-foundation` | `pending` | `@verifier + @unit-tester` | `TBD` | Includes Windows `%LOCALAPPDATA%` default plus `%USERPROFILE%` fallback logic. |
| `HOME-1.u4` | `phase-2-uuid-and-user-state-foundation` | `pending` | `@verifier + @unit-tester` | `TBD` | Helper/API owner; phase 3 regression-proves the behavior through real spawn flows. |
| `HOME-1.e1` | `phase-2-uuid-and-user-state-foundation` | `pending` | `@verifier + @unit-tester` | `TBD` | Covers invalid or unwritable user-root failures. |
| `HOME-1.e2` | `phase-2-uuid-and-user-state-foundation` | `pending` | `@verifier + @unit-tester` | `TBD` | Covers missing `.meridian/id` behavior and the lazy UUID creation boundary. |
| `HOME-1.u3` | `phase-3-runtime-consumers-and-smoke` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | End-to-end proof that repo `.meridian/` no longer regains runtime state. |
| `HOME-1.p1` | `phase-3-runtime-consumers-and-smoke` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | Owned by move-project smoke evidence. |
| `HOME-1.p2` | `phase-3-runtime-consumers-and-smoke` | `pending` | `@verifier + @unit-tester + @smoke-tester` | `TBD` | Owned by operation-level migration plus spawn/session/report smoke. |

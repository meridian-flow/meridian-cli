# Implementation Decisions — R06

Append-only. Covers execution-phase judgment calls. Design decisions remain in `../decisions.md`.

## I01 — Sequential execution despite phase 1+2 independence

Phases 1 (SpawnRequest split) and 2 (RuntimeContext unification) have no file overlap and could be parallelized. Decided sequential — both are small (~2 files, DTO-only), coordination overhead exceeds time savings. Sequential gives cleaner commit history.

## I02 — SpawnRequest as additive type, not breaking change in phase 1

Phase 1 adds SpawnRequest alongside SpawnParams without changing callers. SpawnParams keeps all current fields. Breaking callers into two DTOs requires the factory (phase 3). Alternative (split + migration in one phase) would be too large to verify incrementally.

## I03 — Plan directly rather than spawn separate planner

Design already provides well-specified 8-phase decomposition with file lists, exit criteria, ordering. Planner adds overhead without adding insight for a refactor this well-specified.

## I04 — resolve_policies callers in driving adapters are acceptable

Design exit criteria says `resolve_policies` should only be called from the factory. In practice, driving adapters call it during pre-composition (policy resolution from CLI args / HTTP request / spawn input), then pass the resolved policies through the factory via `PreparedSpawnPlan`. The factory centralizes SpawnParams construction, spec resolution, env building, and fork materialization. Policy resolution is a pre-composition step — each driving adapter has a different input shape.

## I05 — TieredPermissionResolver in server.py is driving-adapter input resolution

Design says `TieredPermissionResolver` should only be in `launch/permissions.py`. The server constructs it from HTTP inputs before passing to the factory. This is input validation, not composition bypass. The factory still does the actual composition.

## I06 — Old LaunchResult in types.py is a different concept

`src/meridian/lib/launch/types.py:LaunchResult` is primary launch result metadata (command, exit_code, chat_id). The new `launch/context.py:LaunchResult` is the post-execution adapter result (session_id from observe_session_id). Different concepts, confusing names. A future rename is warranted but not blocking for R06.

## I07 — Combined phases for efficiency

Combined phases 1+2 (both additive type changes) and phases 4+5+6 (all three driving adapter rewirings) to reduce coordination overhead. Each combined batch was committed atomically with all tests passing.

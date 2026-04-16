# Pre-Planning Notes

## Verified design claims

- P1.1 valid: `src/meridian/lib/ops/spawn/prepare.py:315` calls `resolve_permission_pipeline()` and `src/meridian/lib/ops/spawn/prepare.py:327` calls `harness.build_command(...)`, violating invariant I-2's driving-adapter prohibition list.
- P1.2 valid: `src/meridian/lib/launch/streaming_runner.py:744` defines `execute_with_streaming(...)` on `SpawnRequest`, then `src/meridian/lib/launch/streaming_runner.py:799` rebuilds `launch_context = build_launch_context(...)`, violating I-8.
- P1.3 valid: `src/meridian/lib/launch/context.py:56` defines a launch-layer `RuntimeContext`, while `src/meridian/lib/core/context.py:12` already defines `RuntimeContext` as the core owner named by I-3.
- P2.1 valid: `src/meridian/lib/launch/context.py:234` accepts `dry_run`, then `src/meridian/lib/launch/context.py:240` discards it via `_ = dry_run`.
- P2.2 valid: `src/meridian/lib/launch/request.py:66` types `autocompact: bool | None`, while prepare/execution paths treat it as percent metadata (`src/meridian/lib/ops/spawn/prepare.py:361`, `src/meridian/lib/ops/spawn/execute.py:456`).
- P2.3 valid: `src/meridian/lib/launch/run_inputs.py:33` exposes `build_resolved_run_inputs(...)`, but body is pure pass-through constructor wrapper.
- P3.1 valid: `src/meridian/lib/launch/extract.py:15-18` duplicates artifact filename constants already owned by `src/meridian/lib/launch/constants.py`.
- P3.2 valid: `src/meridian/lib/launch/command.py:82-85` catches broad `TypeError` to decide adapter `project_workspace` calling convention, masking adapter-internal failures.
- P4.2 valid: `src/meridian/lib/launch/process.py:353-361` still calls `build_launch_env(...)` on primary path after command planning, making `process.py` a second composition surface outside `build_launch_context()`.
- Explorer evidence widens phase scope: `src/meridian/lib/launch/plan.py:132-323` still constructs a pre-composed `ResolvedPrimaryLaunchPlan` and performs policy/session/permission/argv work in the driving layer, and `src/meridian/lib/streaming/spawn_manager.py:197` can still call `bundle.adapter.resolve_launch_spec()` directly when no spec is provided.

## Falsified design claims

- None found in code inspection. Cleanup scope matches current code reality.

## Latent risks not in requirements

- `src/meridian/lib/launch/plan.py:35` sets `ResolvedPrimaryLaunchPlan.model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)`, which appears to violate I-5 on its face. This may already be known debt outside listed cleanup items; coder should avoid expanding this pattern and reviewer should call out if touched.
- `src/meridian/lib/launch/command.py:130-144` lets `build_launch_argv(...)` resolve spec/projection internally when `projected_spec` absent. Safe now, but a caller that omits `projected_spec` can still trigger hidden composition outside factory. Cleanup should preserve or tighten sole-owner semantics.
- Primary launch and spawn launch still use different DTO stacks (`LaunchRequest` vs `SpawnRequest`). Full unification is larger than this cleanup; phase should minimize drift, not attempt redesign.
- Harness extension touchpoints are broader than registry alone: adapter bundle registration in harness modules, bootstrap imports in `src/meridian/lib/harness/__init__.py`, default adapter registration in `src/meridian/lib/harness/registry.py`, bundle lookup in `src/meridian/lib/harness/bundle.py`, spawn-param accounting in `src/meridian/lib/harness/launch_spec.py`, permission projection in `src/meridian/lib/harness/projections/permission_flags.py`, and connection bootstrap in `src/meridian/lib/harness/connections/__init__.py`.

## Probe gaps

- Need final code search after implementation to confirm no remaining prohibited direct calls in driving adapters.
- Need runtime verification that primary launch still preserves session/fork behavior if `process.py` is routed through factory-owned env/context logic.
- Need review confirmation whether P4.1 is best solved by code comments/docstring touchpoint inventory rather than dynamic registration refactor.
- Need final confirmation that any `process.py` fork-path exception is either eliminated or explicitly documented as sanctioned architecture, not accidental drift.

## Leaf-distribution hypothesis

- Single phase owns P1.1, P1.2, P1.3, P2.1, P2.2, P2.3, P3.1, P3.2, P4.1, P4.2.
- Final review loop additionally verifies invariant set I-1 through I-13 remains satisfied or improved, with emphasis on I-1, I-2, I-3, I-5, I-8, and I-9.

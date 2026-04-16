# Phase 1 - Launch Core Cleanup

## Scope

Bring launch implementation into alignment with cleanup requirements and invariant file without redesigning unrelated subsystems.

## Claimed leaves

- P1.1 remove preview composition from `prepare.py`
- P1.2 change streaming execution path to consume pre-composed `LaunchContext`
- P1.3 eliminate duplicate `RuntimeContext` naming hazard
- P2.1 remove or implement dead `dry_run` parameter
- P2.2 correct or delete wrong `SpawnRequest.autocompact` field
- P2.3 remove `build_resolved_run_inputs` wrapper
- P3.1 dedupe extract constants
- P3.2 remove `TypeError` masking in workspace projection dispatch
- P4.1 document harness extension touchpoints
- P4.2 route `process.py` through factory or explicitly document second surface

## Expected touched files

- `src/meridian/lib/launch/context.py`
- `src/meridian/lib/launch/request.py`
- `src/meridian/lib/launch/run_inputs.py`
- `src/meridian/lib/launch/command.py`
- `src/meridian/lib/launch/extract.py`
- `src/meridian/lib/launch/streaming_runner.py`
- `src/meridian/lib/launch/process.py`
- `src/meridian/lib/launch/plan.py`
- `src/meridian/lib/streaming/spawn_manager.py`
- `src/meridian/lib/ops/spawn/prepare.py`
- `src/meridian/lib/ops/spawn/execute.py`
- `src/meridian/lib/harness/registry.py`
- `src/meridian/lib/harness/__init__.py`
- `src/meridian/lib/harness/bundle.py`
- `src/meridian/lib/harness/launch_spec.py`
- `src/meridian/lib/harness/connections/__init__.py`
- `src/meridian/lib/harness/projections/permission_flags.py`
- tests/docs only if required by implementation

## Boundaries

- No direct edits to generated `.agents/`.
- No broad harness-registration redesign unless required to satisfy documentation/touchpoint requirement.
- Preserve existing fork/session ordering invariants.
- If keeping a primary-launch fork-path exception, document it explicitly and ensure reviewers can judge it against invariant intent.

## Exit criteria

- No driving-adapter prohibited calls remain in `prepare.py`.
- `execute_with_streaming(...)` no longer rebuilds context from `SpawnRequest`.
- Only one launch/runtime context name remains authoritative for child env ownership.
- Dead/wrong DTO fields/wrappers removed or corrected consistently.
- Workspace projection seam no longer relies on exception-based calling-convention detection.
- Primary launch path and streaming manager path either use factory-owned composition or are explicitly documented as sanctioned exceptions with named touchpoints.
- Verification green: `ruff`, `pyright`, targeted tests, broader tests as needed.
- Final GPT-5.4 review lanes converge with no substantive findings.

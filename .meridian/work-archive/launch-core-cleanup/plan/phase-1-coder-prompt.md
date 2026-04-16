# Phase 1 Implementation Brief

Implement launch-core-cleanup in one coherent patch.

You are not alone in repo. Do not revert others' work. Only edit files needed for this phase. Adjust to existing uncommitted changes if any appear.

Primary goals:

1. Fix invariant violations and cleanup items called out in:
- `.meridian/work/launch-core-cleanup/requirements.md`
- `.meridian/invariants/launch-composition-invariant.md`
- `.meridian/work/launch-core-cleanup/plan/pre-planning-notes.md`
- `.meridian/work/launch-core-cleanup/plan/phase-1-launch-core-cleanup.md`

2. Minimum required outcomes:
- Remove preview-path composition from `src/meridian/lib/ops/spawn/prepare.py`.
- Change streaming executor path so `execute_with_streaming(...)` consumes pre-composed launch data instead of rebuilding from `SpawnRequest`.
- Eliminate duplicate `RuntimeContext` naming hazard.
- Remove or correct dead/wrong DTO fields and wrappers: `dry_run`, `SpawnRequest.autocompact`, `build_resolved_run_inputs`.
- Dedupe launch extract constants.
- Replace `apply_workspace_projection()` exception-based calling-convention dispatch with explicit logic that does not mask adapter errors.
- Resolve residual composition drift in `src/meridian/lib/launch/process.py`, `src/meridian/lib/launch/plan.py`, and `src/meridian/lib/streaming/spawn_manager.py`, or document sanctioned exceptions clearly enough for invariant reviewers to judge.
- Document harness extension touchpoints instead of silently relying on scattered bootstrap/registration behavior.

3. Boundaries:
- Preserve fork/session ordering invariants.
- Do not redesign unrelated launch architecture beyond this cleanup.
- Prefer deletion and direct constructor use over wrappers where possible.
- If you keep any explicit second composition surface or fork-path exception, name and document it in code comments/docstrings near the owning seam.

4. Verification:
- Run targeted tests for touched launch/spawn areas.
- Run `uv run ruff check .`
- Run `uv run pyright`
- Run broader tests as needed to get confidence on touched surfaces.

5. Report back:
- What changed
- Files changed
- Tests/checks run with results
- Open risks or intentional deviations, if any

Own these files/modules unless directly-required tests/docs force expansion:
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

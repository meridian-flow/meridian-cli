# R06 launch fs update

Update agent-facing mirror docs after launch-core-refactor (R06).

## Scope

Edit only:

- `.meridian/fs/launch/overview.md`
- `.meridian/fs/launch/process.md`
- `.meridian/fs/overview.md`

Do not edit user-facing `docs/`. Do not edit source code.

## Required architecture facts

- Launch subsystem now uses hexagonal composition centered on `build_launch_context()` in `src/meridian/lib/launch/context.py`.
- Factory owns composition. Driving adapters do not compose; they build a `SpawnRequest` + `LaunchRuntime`, call factory, then execute/observe.
- Three driving adapters to capture:
  - primary CLI path
  - spawn subprocess path
  - app/streaming HTTP path
- Core typed seam:
  - `SpawnRequest` = caller intent DTO
  - `LaunchRuntime` = environment/surface/runtime inputs
  - `LaunchContext` = composed launch state
- Typed enums to mention where useful:
  - `LaunchMode`
  - `LaunchArgvIntent`
  - `LaunchCompositionSurface`
- Invariant set is now 13 items. Source of truth:
  - `.meridian/invariants/launch-composition-invariant.md`

## Dev-principles facts to reflect

- Composition happens in one place.
- Driving adapters call factory; they do not compose directly.
- DTOs do not cache derived state.
- Mirror is observational: describe what exists in code now, not aspirational rules beyond what current code/invariant file establishes.

## Current code facts to preserve

- `src/meridian/lib/launch/process.py` remains mechanism-heavy:
  - primary path starts spawn row, materializes fork only after row exists, rebuilds runtime context with actual spawn/report/work paths, runs subprocess, finalizes inline, then calls adapter `observe_session_id()` once post-execution
- `src/meridian/lib/ops/spawn/prepare.py` uses factory for dry-run/prepare normalization
- `src/meridian/lib/ops/spawn/execute.py` uses factory before streaming execution and background worker execution
- `src/meridian/lib/app/server.py` and `src/meridian/cli/streaming_serve.py` use factory with `SPEC_ONLY`

## Mined reasoning from archived work

From `.meridian/work-archive/launch-core-cleanup/decisions.md` and `plan/overview.md`:

- Cleanup intentionally centralized shared composition seam instead of splitting work by adapter because files and invariants overlapped heavily.
- Review focus emphasized semantic invariant compliance and consistency across launch code.

## Source files to read

- `.meridian/fs/launch/overview.md`
- `.meridian/fs/launch/process.md`
- `.meridian/fs/overview.md`
- `.meridian/invariants/launch-composition-invariant.md`
- `src/meridian/lib/launch/context.py`
- `src/meridian/lib/launch/request.py`
- `src/meridian/lib/launch/process.py`
- `src/meridian/lib/launch/plan.py`
- `src/meridian/lib/ops/spawn/prepare.py`
- `src/meridian/lib/ops/spawn/execute.py`
- `src/meridian/lib/app/server.py`
- `src/meridian/cli/streaming_serve.py`

## Deliverable

Concise, accurate fs docs that make current launch architecture legible to future agents.

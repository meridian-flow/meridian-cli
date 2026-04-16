# Launch Core Cleanup Requirements

Follow-up to R06 launch-core-refactor. Four independent reviewers found gaps between the architecture's declared invariants and the actual implementation.

## Priority 1 — Invariant Violations

### P1.1 — Eliminate `prepare.py` composition (I-2 violation)

`prepare.py` is on the driving-adapter prohibition list but directly calls:
- `resolve_permission_pipeline()` at line 315
- `harness.build_command()` at line 327
- `resolve_policies()` via shim at line 205

**Fix:** Route preview-command construction through `build_launch_context(dry_run=True)` or expose a preview-only stage under the factory.

### P1.2 — Fix `execute_with_streaming` composition (I-8 violation)

`execute_with_streaming` accepts `SpawnRequest + LaunchRuntime` and calls `build_launch_context()` internally. Executors should accept pre-composed `LaunchContext`.

**Fix:** Move `build_launch_context()` call into driving adapters; executor accepts `LaunchContext` only.

### P1.3 — Merge duplicate `RuntimeContext` classes (I-3 violation)

Two classes named `RuntimeContext`:
- `core/context.py` — Pydantic model, used by executor path
- `launch/context.py` — dataclass, used by streaming path

Both read same `MERIDIAN_*` vars, both produce env dicts. Name collision is a wrong-import hazard.

**Fix:** Rename `launch/context.py:RuntimeContext` to `ChildEnvContext` or merge into single class.

## Priority 2 — Dead/Wrong Code

### P2.1 — Remove or implement `dry_run` parameter

`context.py:241` immediately discards `dry_run`:
```python
_ = dry_run
```

**Fix:** Remove parameter if unused, or implement dry-run behavior.

### P2.2 — Fix `SpawnRequest.autocompact` type

`SpawnRequest.autocompact: bool | None` but everywhere else is `int | None`. Field is never read.

**Fix:** Change type to `int | None` and wire to resolution path, or delete field.

### P2.3 — Delete `build_resolved_run_inputs` wrapper

37-line function that just passes 14 kwargs to constructor. No transformation logic.

**Fix:** Call `ResolvedRunInputs(...)` directly at callsites.

## Priority 3 — Consistency Fixes

### P3.1 — Dedupe constants in `extract.py`

`extract.py` redefines `_REPORT_FILENAME`, `_OUTPUT_FILENAME`, etc. already in `constants.py`.

**Fix:** Import from `constants.py`.

### P3.2 — Fix `apply_workspace_projection` TypeError catch

Catches `TypeError` to select calling convention — masks real errors inside adapter.

**Fix:** Use `inspect.signature` at registration time or standardize calling convention.

## Priority 4 — Extension Seam Cleanup

### P4.1 — Document or fix harness extension path

Adding a new harness requires editing central switchboards (`__init__.py`, `registry.py`, `permission_flags.py`). Not actually open for extension.

**Fix:** Either make registration dynamic or document the required touchpoints explicitly.

### P4.2 — Eliminate parallel composition in `process.py`

Primary launch path uses `resolve_primary_launch_plan + build_launch_env + build_launch_argv` — a second composition surface not covered by the 13 invariants.

**Fix:** Route through `build_launch_context()` or explicitly name as second composition surface.

## Constraints

- 673 tests must continue passing
- No new invariant violations
- pyright/ruff clean

## Source

Findings from 4 parallel reviewers:
- p2005: Drift gate invariant compliance (sonnet)
- p2006: SOLID principles and extensibility (gpt-5.4)
- p2007: Simplicity (sonnet)
- p2008: Consistency (sonnet)

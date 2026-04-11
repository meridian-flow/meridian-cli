# S031: No circular imports

- **Source:** design/edge-cases.md E31 + design/typed-harness.md §Import Topology (revision round 3 convergence pass)
- **Added by:** @design-orchestrator (design phase, updated in revision round 3 convergence pass)
- **Tester:** @verifier
- **Status:** pending

## Given
Current typed module DAG (authoritative list in `design/typed-harness.md §Import Topology`):

- `launch/launch_types.py` — leaf types (`PermissionResolver`, `SpecT`, `ResolvedLaunchSpec`, `PreflightResult`, `PermissionConfig`) — **lives under `launch/`, not `harness/`**
- `launch/context.py`, `launch/constants.py`, `launch/text_utils.py`
- `harness/ids.py` — `HarnessId`, `TransportId` enums (zero in-package imports)
- `harness/adapter.py`, `harness/connections/base.py`, `harness/extractors/base.py`
- `harness/bundle.py` — glues adapter + spec + connections + extractor
- `harness/launch_spec.py` — aggregates every adapter's `handled_fields` for K9
- `harness/claude_preflight.py` — Claude-specific preflight helpers
- `harness/projections/_guards.py`
- `harness/projections/project_claude.py`
- `harness/projections/project_codex_subprocess.py`
- `harness/projections/project_codex_streaming.py` (+ optional `_fields`, `_appserver`, `_rpc` split modules when line budget triggers)
- `harness/projections/project_opencode_subprocess.py`
- `harness/projections/project_opencode_streaming.py`
- `harness/connections/*.py`
- `harness/extractors/*.py`
- `harness/__init__.py` — eager bootstrap of concrete adapters, projections, extractors, then `_enforce_spawn_params_accounting()`

## When
Modules are imported in fresh interpreters and pyright runs.

## Then
- Imports succeed without cycle errors in the order prescribed by `harness/__init__.py` §Bootstrap Sequence.
- pyright resolves types with no cycle-induced failures.
- A follow-up `from meridian.lib.harness import SpawnManager; SpawnManager` reference resolves (confirms the eager bootstrap has run and `_REGISTRY` is populated).

## Verification
- Scripted per-module import smoke test iterates every module listed above (authoritative list in the design doc §Import Topology, not inlined here) in isolated `importlib` invocations.
- `uv run pyright` full-tree check.
- Explicit assert: importing `meridian.lib.harness` triggers `_enforce_spawn_params_accounting()` exactly once — verified via a test double that counts calls, or via a module-level sentinel.
- Negative test: introduce a deliberate `from meridian.lib.harness.projections.project_claude import ...` at the top of `launch/launch_types.py` (fixture patch), assert import raises `ImportError` due to the induced cycle, and assert the baseline graph does not trigger this.

## Result (filled by tester)
_pending_

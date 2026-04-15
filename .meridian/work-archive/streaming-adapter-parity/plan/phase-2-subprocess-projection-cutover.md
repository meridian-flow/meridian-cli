# Phase 2: Subprocess Projection Cutover

## Scope

Reimplement subprocess command construction on top of resolved specs and delete the strategy framework once command parity is proven.

This phase keeps streaming untouched. The subprocess path remains the stable reference, so the gate is byte-for-byte command parity for the current adapters.

## Files to Modify

- `src/meridian/lib/harness/common.py`
  Remove `FlagEffect`, `FlagStrategy`, `StrategyMap`, `_SKIP_FIELDS`, and `build_harness_command()` after the adapters no longer depend on them.
- `src/meridian/lib/harness/claude.py`
  Rewrite `build_command()` to resolve a `ClaudeLaunchSpec` first, then explicitly project it to CLI args.
- `src/meridian/lib/harness/codex.py`
  Rewrite `build_command()` to resolve a `CodexLaunchSpec` first, preserve current subcommand ordering, and keep `-o report_path` behavior intact.
- `src/meridian/lib/harness/opencode.py`
  Rewrite `build_command()` to resolve an `OpenCodeLaunchSpec` first and project session/fork flags explicitly.
- `tests/harness/test_launch_spec_parity.py` (new)
  Start the parity file with subprocess-only command regression cases covering fresh, resume, fork, effort, permissions, and extra args.
- `tests/ops/test_spawn_prepare_fork.py`
  Keep at least one dry-run assertion that the preview command shape is unchanged after the refactor.

## Dependencies

- Requires: Phase 1
- Produces: the stable spec-backed subprocess reference path
- Blocks: Phase 3 through Phase 6

## Interface Contract

`build_command()` now follows this shape:

```python
spec = self.resolve_launch_spec(run, perms)
command = self._project_cli_command(spec)
```

Each CLI projection must declare a machine-checkable field guard for the spec fields it handles. Unsupported fields must be explicitly documented rather than omitted silently.

## Patterns to Follow

- Preserve current argument ordering exactly; use the existing adapter implementations as the ordering reference.
- Keep prompt handling explicit (`"-"` for stdin-capable non-interactive modes, positional text for interactive modes).
- Resolve permission flags by calling `spec.permission_resolver.resolve_flags(self.id)` at projection time.

## Verification Criteria

- [ ] `uv run pytest-llm tests/harness/test_launch_spec.py tests/harness/test_launch_spec_parity.py`
- [ ] `uv run pytest-llm tests/ops/test_spawn_prepare_fork.py`
- [ ] `uv run pyright`
- [ ] For each harness, the regression fixture demonstrates identical command lists before and after the cutover for representative cases

## Staffing

- Builder: `@coder` on `gpt-5.3-codex`
- Testing lanes: `@verifier` on `gpt-5.4-mini`, `@unit-tester` on `gpt-5.2`

## Constraints

- Do not touch streaming connection code here.
- Do not remove fields from `ConnectionConfig` here.
- If any adapter cannot reproduce existing command order exactly, stop and log the discrepancy before deleting the old strategy helpers.

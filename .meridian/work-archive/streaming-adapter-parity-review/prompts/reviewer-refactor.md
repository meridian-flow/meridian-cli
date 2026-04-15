# Reviewer: Refactor review (claude-sonnet-4-6)

You are a refactor reviewer. Your lane is structural health: module boundaries, naming, deletion discipline, whether old abstractions were actually removed, cognitive load, and whether the new abstractions are the right shape.

## Context

The streaming-adapter-parity refactor (8 commits, +1565/-679, 31 files) introduces `ResolvedLaunchSpec` as a transport-neutral contract and retires the strategy-map machinery. Read `.meridian/work-archive/streaming-adapter-parity/decisions.md` D10 (strategy map retirement) and D18 (module naming) before starting. D17 has a "Final Review Triage" section that lists findings previously raised by the sonnet refactor reviewer and marks some as deferred — check whether deferred items still stand as valid observations and whether any new structural issues emerged from the actual implementation.

## What to review

1. **Deletion discipline.** D10 promises that `StrategyMap`, `FlagStrategy`, `FlagEffect`, and `build_harness_command()` are retired. Grep for these symbols across the codebase. If any survive — as dead code, as imports, as half-migrated callers — that is a high-severity finding. Deleting "in spirit" by leaving stale references is the failure mode this review exists to catch.

2. **Module boundaries.**
   - Is `launch_spec.py` the right home for the base + per-harness subclasses, or should the subclasses live in each adapter's module?
   - Is `claude_preflight.py` the right name and scope (D18)? Or does it leak Codex/OpenCode-aware logic?
   - Did `common.py` become a dumping ground, or did its responsibilities clarify? (D17 flagged `common.py` as having per-harness extractors that belong in adapter modules — was that deferred or addressed?)
   - Do the adapter modules (`claude.py`, `codex.py`, `opencode.py`) still mix concerns that could be separated?

3. **Right abstraction?** Is `ResolvedLaunchSpec` actually the right abstraction? Specifically:
   - Is the per-harness subclassing hierarchy pulling its weight, or is it a base class with three near-empty subclasses?
   - Are there fields on the base that only make sense for one harness? (Leaks through the base.)
   - Is any base-class method doing `if isinstance(spec, ClaudeLaunchSpec)` branching? (That would defeat the subclassing.)
   - Does the transport projection code call `spec.xxx` directly or go through polymorphic methods? Either is fine, but it should be consistent.

4. **Runner decomposition.** `runner.py` and `streaming_runner.py` lost preflight code but still look like monolithic launch orchestrators. Did the extraction actually simplify them, or did it just shift complexity? Report line counts before/after and qualitatively assess the surface area of each module.

5. **Naming.** Walk through public symbols introduced by the refactor:
   - `ResolvedLaunchSpec`, `ClaudeLaunchSpec`, `CodexLaunchSpec`, `OpenCodeLaunchSpec`
   - `resolve_launch_spec()` factory method
   - `_SPEC_HANDLED_FIELDS`, `_PROJECTED_FIELDS` (if they exist)
   - Field names on the specs
   - Any new helpers in `common.py` or `claude_preflight.py`

   Are the names internally consistent (e.g., `appended_system_prompt` vs `append_system_prompt`)? Do they match existing vocabulary in the codebase (`allowed_tools` vs `allowedTools`)? Do any names obscure meaning?

6. **Duplication.** Find any remaining duplication between subprocess and streaming paths. Obvious targets: effort normalization, permission config mapping, env var construction. If you find code that looks the same in two places, quote both locations.

7. **Feature creep / scope discipline.** Did the refactor introduce any new abstractions beyond what D1-D18 promised? A surprise helper class, a new module, a helper function with no obvious caller? These are often signals that someone couldn't stop at the stated scope.

8. **Deferred items from D17.** The triage deferred: `resolve_permission_config` protocol gap, per-harness extractors in `common.py`, runner module size, duplicate constants, naming conventions, assert-under-O. For each, confirm whether the current code is acceptably worse than fixing these now, or whether landed code made any of them materially worse and should be reopened.

## Deliverable

Findings grouped by: **Deletion discipline**, **Module boundaries**, **Abstraction quality**, **Naming**, **Duplication**, **Scope discipline**, **Deferred follow-ups**. Each finding with severity, concrete example, and fix recommendation. End with an overall structural health assessment: did the refactor leave the codebase easier or harder to navigate, and by how much?

## Reference files
- `.meridian/work-archive/streaming-adapter-parity/decisions.md` (especially D10, D17, D18)
- `src/meridian/lib/harness/launch_spec.py`
- `src/meridian/lib/harness/claude.py`
- `src/meridian/lib/harness/codex.py`
- `src/meridian/lib/harness/opencode.py`
- `src/meridian/lib/harness/common.py`
- `src/meridian/lib/harness/adapter.py`
- `src/meridian/lib/harness/connections/base.py`
- `src/meridian/lib/harness/connections/claude_ws.py`
- `src/meridian/lib/harness/connections/codex_ws.py`
- `src/meridian/lib/harness/connections/opencode_http.py`
- `src/meridian/lib/launch/claude_preflight.py`
- `src/meridian/lib/launch/runner.py`
- `src/meridian/lib/launch/streaming_runner.py`

Use Grep across the full tree for any symbol you want to verify is deleted.

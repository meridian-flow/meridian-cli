# Review — streaming-parity-fixes v2 design, type contract & projection completeness focus

You are reviewing the **v2 design** for streaming adapter parity. Your focus is the type system and the projection completeness machinery — the parts that were supposed to exist in v1 but shipped half-formed, which is why p1411 reviewers found 4 HIGH issues.

## Your focus area

**Typed harness contracts and projection completeness guards.** Specifically:

1. **Generic type binding.** Does `HarnessAdapter[SpecT]` / `HarnessConnection[SpecT]` / `HarnessBundle[SpecT]` actually give pyright the leverage to catch every misuse — base spec passed to typed connection, adapter without `resolve_launch_spec`, a connection registered with the wrong spec type? Or are there gaps that a `cast` or a missing annotation would silently bypass?
2. **`ImportError` guards.** Are the projection completeness guards in `projections/*.py` (each with its own `_PROJECTED_FIELDS` frozenset) sound? Do they cover both the "new field on spec, projection forgets it" case (E5) and the "new field on SpawnParams, factory forgets it" case (E6)? Do they run at import time with no `assert`? Do they name the file to edit in the error message? Will they fire under `python -O`?
3. **`_SPEC_HANDLED_FIELDS` + `_SPEC_DELEGATED_FIELDS` split.** Does the split actually prevent the L2 lie ("listed as handled but the factory does nothing")? What happens when a developer adds a field to one set but not the other?
4. **Single declared cast at dispatch.** Is there exactly one `cast` in the harness layer, at the dispatch boundary, and is it narrow enough to be auditable? Are there hidden casts via `# type: ignore` that should have been caught?
5. **Byte-equal arg tail contract.** Is the canonical order locked in by tests, not just documented? Can the parity contract (`subprocess_args[len(BASE):] == streaming_args[len(BASE):]`) be verified at CI time without running the real harness binaries?
6. **`_AgentNameMixin`, `HarnessBundle`, Protocol inheritance.** Are these structural choices actually enforceable by pyright, or do they devolve into documentation comments the next developer ignores?

## What to read

- `.meridian/work/streaming-parity-fixes/design/typed-harness.md` (primary)
- `.meridian/work/streaming-parity-fixes/design/launch-spec.md`
- `.meridian/work/streaming-parity-fixes/design/transport-projections.md`
- `.meridian/work/streaming-parity-fixes/design/overview.md`
- `.meridian/work/streaming-parity-fixes/decisions.md` (D1–D10, D18)
- `.meridian/work/streaming-parity-fixes/scenarios/S001`, `S002`, `S004`, `S005`, `S006`, `S015`, `S021`, `S023`, `S030`, `S031`, `S034`, `S035`
- `.meridian/spawns/p1411/report.md` (findings H4 and M1–M3, M8)
- Current source for comparison:
  - `src/meridian/lib/harness/launch_spec.py`
  - `src/meridian/lib/harness/adapter.py`
  - `src/meridian/lib/harness/connections/*.py`

## Deliverable

Report findings with severity (CRITICAL / HIGH / MEDIUM / LOW). For each finding, include the file and section reference, the concrete scenario the gap enables, and a suggested fix.

A CRITICAL finding is: the v2 design leaves a hole through which one of the p1411 HIGH findings can recur. If you find one, say so loudly.

End with an overall verdict: **Converged / Needs revision / Reject and redesign**.

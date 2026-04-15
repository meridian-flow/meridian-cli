# Explorer: Completeness guards (both directions)

You are an explorer. Do not make code changes. Report facts only.

## Task

There are two completeness guards that matter for this refactor:

1. **SpawnParams → ResolvedLaunchSpec** — catches new `SpawnParams` fields that the spec factory forgot to handle.
2. **ResolvedLaunchSpec → transport projection** (D15) — catches new spec fields that a transport projection (CLI args / JSON-RPC params / HTTP payload) forgot to handle.

Verify both guards actually exist and actually catch drift.

## Specific questions to answer

1. **Guard 1 (SpawnParams → spec):** Locate the guard. Likely in `src/meridian/lib/harness/common.py` or `launch_spec.py`. Quote the exact assertion, the set/frozenset it uses, and show where the assertion is triggered (import time? test time?).

2. **Guard 2 (spec → CLI args, subprocess path):** Locate the transport projection for `build_command()`. Quote any `_PROJECTED_FIELDS` or equivalent frozenset, and show the assertion that ties it to the spec subclass. If no such guard exists, state that plainly — D15 requires it.

3. **Guard 2 (spec → JSON-RPC params, Codex streaming):** Same check inside `connections/codex_ws.py`.

4. **Guard 2 (spec → HTTP payload, OpenCode streaming):** Same check inside `connections/opencode_http.py`.

5. **Guard 2 (spec → CLI args, Claude streaming):** Same check inside `connections/claude_ws.py`.

6. **Drift simulation.** For each guard that exists, manually simulate what happens if someone adds a new field `foo: str | None = None` to the relevant spec. Walk through which guard fires, at what moment (import, test run, first spawn), and what the error message looks like. If a guard would NOT catch the new field, state that and explain the path by which the field silently falls through.

7. **Check the D17 triage follow-up.** Was `mcp_tools` removed from `_SPEC_HANDLED_FIELDS` or given a truthful comment as promised in the decision log? Quote the current state.

8. **Import time vs test time.** For each guard, state which. Import-time guards are strictly stronger because they fire even if nobody runs tests.

## Reference files
- `src/meridian/lib/harness/launch_spec.py`
- `src/meridian/lib/harness/common.py`
- `src/meridian/lib/harness/claude.py`
- `src/meridian/lib/harness/codex.py`
- `src/meridian/lib/harness/opencode.py`
- `src/meridian/lib/harness/connections/claude_ws.py`
- `src/meridian/lib/harness/connections/codex_ws.py`
- `src/meridian/lib/harness/connections/opencode_http.py`
- `src/meridian/lib/ops/spawn/params.py` (or wherever `SpawnParams` is defined — find it)
- `.meridian/work-archive/streaming-adapter-parity/decisions.md` (D2, D15, D17)

## Deliverable

A structured report. For each guard: does it exist, where, what does it assert, does it fire at import or test time, and would it catch a new spec field. Quote everything.

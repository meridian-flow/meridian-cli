# S012: Subprocess Claude dedupes parent `--allowedTools` (parity)

- **Source:** design/edge-cases.md E12 + p1411 finding H2 (parity half)
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @smoke-tester
- **Status:** verified

## Given
Identical inputs to S011 but routed through the subprocess runner:
- `CLAUDECODE=1`.
- Parent `.claude/settings.json` grants `["Read", "Bash"]`.
- `ExplicitToolsResolver(allowed_tools=("Read", "Edit"))`.

## When
The subprocess runner builds the Claude command via the shared `project_claude_spec_to_cli_args`.

## Then
- The final command contains **exactly one** `--allowedTools` flag with the same deduped union value as S011.
- Arg tail (positions after the base command `claude`) is byte-identical to the streaming path for the same spec.
- No divergence in handling between subprocess and streaming.

## Verification
- Pair with S011: call both projections in the same test and assert `subprocess_args[len(SUBPROCESS_BASE):] == streaming_args[len(STREAMING_BASE):]`.
- Smoke test: run the real subprocess spawn, capture the command from process metadata, and compare to the streaming capture from S011.
- If the two outputs ever diverge for the same spec, the shared projection promise is broken and this scenario fails.

## Result (filled by tester)
- **Date:** 2026-04-10
- **Status:** verified
- **Tests:** `tests/harness/test_launch_spec_parity.py::test_claude_projection_dedupes_resolver_internal_allowed_tools` ([line 324](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:324)), `tests/harness/test_launch_spec_parity.py::test_claude_cross_transport_parity_on_semantic_fields` ([line 810](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:810))
- **Commands:**
  - `uv run pytest-llm tests/harness/test_launch_spec_parity.py -k claude -v` -> `21 passed, 16 deselected`
- **Evidence:**
  - The same spec projected against subprocess and streaming base commands yields byte-equal tails after each base prefix.
  - Deduped `--allowedTools` behavior is shared because both transports call `project_claude_spec_to_cli_args`.

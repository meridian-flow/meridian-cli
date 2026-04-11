# S011: Streaming Claude resolver-internal `--allowedTools` dedupe

- **Source:** design/edge-cases.md E11 + p1411 finding H2
- **Added by:** @design-orchestrator (design phase)
- **Updated by:** @design-orchestrator (revision round 3 — scope clarified)
- **Tester:** @smoke-tester (+ @unit-tester for projection unit)
- **Status:** verified

## Scope
Resolver-internal dedupe only. This scenario exercises the case where the Claude resolver merges **multiple internal sources** (parent-forwarded permissions + explicit resolver tools + profile defaults) and emits a single deduped `--allowedTools` flag. It does NOT cover the user-`extra_args` boundary — that is S023, which forwards both flags verbatim.

## Given
- `CLAUDECODE=1` in the parent environment.
- Parent `.claude/settings.json` grants `allowedTools=["Read", "Bash"]`.
- Spawn uses `ExplicitToolsResolver(allowed_tools=("Read", "Edit"))`.
- Streaming runner invokes `read_parent_claude_permissions` preflight.
- `extra_args = ()` — no user passthrough `--allowedTools` (see S023 for that case).

## When
The streaming runner builds the Claude command via `project_claude_spec_to_cli_args`.

## Then
- The final launched command contains **exactly one** `--allowedTools` flag in the canonical position.
- Its value is the deduped order-preserving union: `Read,Edit,Bash` (or equivalent canonical ordering defined in the projection).
- The dedupe happens entirely inside the resolver + projection layer (both are meridian-internal); it does not touch user `extra_args`.
- No duplicate flags. No dropped tools. No silent overwrite by the later flag.
- Byte-identical to the subprocess output for the same inputs (paired with S012).

## Verification
- Unit test: construct the scenario inputs, call `project_claude_spec_to_cli_args`, assert `list.count("--allowedTools") == 1` and the value matches the expected union.
- Smoke test: launch a real streaming Claude spawn with `CLAUDECODE=1`, parent settings file populated, and inspect the process args (via `ps`, `/proc/<pid>/cmdline`, or command logging) for exactly one `--allowedTools` flag.
- Delta test: temporarily disable the projection's dedupe and confirm this test fails.

## Result (filled by tester)
- **Date:** 2026-04-10
- **Status:** verified with extra coverage
- **Tests:** `tests/harness/test_launch_spec_parity.py::test_claude_projection_dedupes_resolver_internal_allowed_tools` ([line 324](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:324)), `tests/harness/test_launch_spec_parity.py::test_claude_projection_dedupes_duplicate_csv_values_within_managed_allowed_tools` ([line 432](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:432)), `tests/harness/test_launch_spec_parity.py::test_claude_adapter_preflight_expands_parent_permissions_with_helper` ([line 538](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:538)), `tests/harness/test_launch_spec_parity.py::test_claude_cross_transport_parity_on_semantic_fields` ([line 810](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:810))
- **Commands:**
  - `uv run pytest-llm tests/harness/test_launch_spec_parity.py -k claude -v` -> `21 passed, 16 deselected`
- **Evidence:**
  - Projection consumes adapter-preflight parent allowlist sentinel (`--meridian-parent-allowed-tools`) and merges it with resolver `--allowedTools` output into one deduped managed flag.
  - Streaming-base projection produced exactly one `--allowedTools` value `Read,Edit,Bash` in deterministic order, with no duplicate managed flags.
  - Added adversarial coverage for duplicate CSV values inside one managed token (`Bash,Bash,Edit`) plus parent-forwarded values (`Edit,Read,Read`), proving resolver-internal dedupe stays order-preserving and never leaks the internal sentinel to the CLI.

# S015: Claude spec round-trip with every field populated

- **Source:** design/edge-cases.md E15 + p1411 M3/H2
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @unit-tester
- **Status:** verified

## Given
A `ClaudeLaunchSpec` fixture with every relevant field populated.

## When
Projected through subprocess and streaming Claude projections.

## Then
- Canonical ordering is preserved.
- Arg tails are byte-equal across transports.
- Permission flags are deduped/merged exactly once.

## Verification
- Parametrized table maps each `ClaudeLaunchSpec` field to exact expected representation:
  flag pair, merged-tail effect, or explicit delegation target.
- Tests assert table coverage for all `model_fields`.
- Parity assertion checks subprocess tail equals streaming tail.

## Result (filled by tester)
- **Date:** 2026-04-10
- **Status:** verified
- **Tests:** `tests/harness/test_launch_spec_parity.py::test_claude_projection_field_mapping_table_covers_every_field` ([line 448](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:448)), `tests/harness/test_launch_spec_parity.py::test_claude_cross_transport_parity_on_semantic_fields` ([line 810](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:810))
- **Commands:**
  - `uv run pytest-llm tests/harness/test_launch_spec_parity.py -k claude -v` -> `21 passed, 16 deselected`
- **Evidence:**
  - Field mapping table asserts coverage for every `ClaudeLaunchSpec.model_fields` entry and validates each field's projection/delegation behavior.
  - Shared projection keeps subprocess/streaming tails byte-equal for a fully-populated Claude spec.

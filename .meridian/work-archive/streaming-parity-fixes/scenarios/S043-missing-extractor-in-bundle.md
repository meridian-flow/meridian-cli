# S043: `HarnessBundle` missing an extractor fails registration

- **Source:** design/edge-cases.md E49 + decisions.md K6 (revision round 3)
- **Added by:** @design-orchestrator (revision round 3)
- **Tester:** @unit-tester
- **Status:** verified

## Given
A developer constructs `HarnessBundle(harness_id=..., adapter=..., spec_cls=..., extractor=None, connections={...})` or omits the `extractor` field entirely.

## When
`register_harness_bundle(bundle)` runs.

## Then
- Registration raises at import time — either via Pydantic/dataclass type-check (if `extractor: HarnessExtractor[SpecT]` is non-optional) or via an explicit non-None validation in `register_harness_bundle`.
- No runner ever reaches `bundle.extractor.detect_session_id_from_artifacts(...)` with `None`.

## Verification
- Unit test: construct a bundle with `extractor=None` (or a mock without `detect_session_id_from_artifacts`) and assert `register_harness_bundle(...)` or the dataclass constructor raises.
- Unit test: assert `HarnessBundle` type hints on `extractor` forbid `None` (pyright-level check or `typing.get_type_hints` inspection).
- Positive test: every harness bundle registered in `harness/__init__.py` has a non-None extractor.

## Result (filled by tester)
verified 2026-04-11

- Evidence:
  - `tests/harness/test_launch_spec_parity.py:528` — `test_bundle_registration_requires_extractor`
  - `tests/harness/test_launch_spec_parity.py:606` — `test_registered_harness_bundles_have_extractors_and_connections`
- Notes:
  - `extractor=None` fails registration immediately, and all production bundles now verify non-`None` extractors at bootstrap.

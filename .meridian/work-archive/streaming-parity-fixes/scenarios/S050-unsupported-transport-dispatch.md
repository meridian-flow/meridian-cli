# S050: `(harness, transport)` dispatch for an unsupported transport raises `KeyError`

- **Source:** design/edge-cases.md E45 + decisions.md K1 (revision round 3)
- **Added by:** @design-orchestrator (revision round 3)
- **Tester:** @unit-tester
- **Status:** verified

## Given
A registered `HarnessBundle` for a harness whose `connections: Mapping[TransportId, ...]` only contains some transports (e.g., Claude supports subprocess and streaming; a hypothetical fourth transport `TransportId.HTTP` is not registered).

## When
Dispatch calls `get_connection_cls(HarnessId.CLAUDE, TransportId.HTTP)` or the dispatch guard in `SpawnManager.start_spawn` selects a transport the bundle does not support.

## Then
- A `KeyError` is raised with a message like `"harness claude has no connection for transport http"` — naming both the harness and the transport for diagnosability.
- No default / fallback connection is silently selected. No `AttributeError` crash deep in connection bootstrapping.
- The registry state is untouched (no mutation on lookup failure).

## Verification
- Unit test: register a fixture bundle with a subset of transports, call `get_connection_cls` for a missing transport, assert `KeyError` and the message contains both identifiers.
- Unit test: verify every currently-registered production bundle has a non-empty `connections` mapping and includes at least the transports required by the runner matrix.
- Regression: remove the `TransportId.STREAMING` entry from the Codex bundle, run the dispatch for a streaming spawn, assert `KeyError` at dispatch — not a downstream crash.

## Result (filled by tester)
verified 2026-04-11

- Evidence:
  - `tests/harness/test_launch_spec_parity.py:564` — `test_get_connection_cls_rejects_unsupported_transport`
  - `tests/test_spawn_manager.py:546` — `test_spawn_manager_dispatch_raises_keyerror_when_streaming_transport_missing`
  - `tests/harness/test_launch_spec_parity.py:587` — `test_bundle_registration_rejects_empty_connections`
  - `tests/harness/test_launch_spec_parity.py:545` — `test_bundle_registration_rejects_unsupported_transport_key`
- Notes:
  - Unsupported `(harness, transport)` lookups fail with `KeyError` at bundle lookup, and registration blocks empty or invalid transport maps before dispatch.

# S035: All connections satisfy the same `HarnessConnection` surface

- **Source:** design/edge-cases.md E35
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @unit-tester
- **Status:** verified

## Given
v2 uses a single `HarnessConnection[SpecT]` ABC (facet protocols removed). Concrete classes:

- `ClaudeConnection(HarnessConnection[ClaudeLaunchSpec])`
- `CodexConnection(HarnessConnection[CodexLaunchSpec])`
- `OpenCodeConnection(HarnessConnection[OpenCodeLaunchSpec])`

## When
Pyright and runtime inheritance checks execute.

## Then
- All three are subclasses of `HarnessConnection`.
- All abstract methods are implemented.
- Removing any required method from one implementation produces pyright error and runtime instantiation failure.

## Verification
- Parametrized `issubclass` checks across concrete classes.
- Pyright check across connections package.
- Negative scratch test removing one abstract method confirms failure path.

## Result (filled by tester)
verified 2026-04-11

Evidence:
- Prior unit-test evidence:
  - `uv run pyright` => `0 errors`.
  - `uv run pytest-llm tests/exec/test_lifecycle.py -v`:
    - `test_all_streaming_connections_bind_harness_connection_protocol` passed (issubclass + generic spec binding + instantiation for Claude/Codex/OpenCode).
  - Negative scratch proof (not committed): created an incomplete subclass missing `send_cancel` and verified:
    - `uv run pyright /tmp/meridian_s035_negative_abc.py` reports `Cannot instantiate abstract class ... "HarnessConnection.send_cancel" is not implemented`.
    - `uv run python /tmp/meridian_s035_negative_abc.py` raises `TypeError: Can't instantiate abstract class ... without an implementation for abstract method 'send_cancel'`.
- Verifier pyright/runtime cross-check:
  - `uv run pyright src/meridian/lib/harness/connections/` -> `0 errors, 0 warnings, 0 informations`
  - `uv run pyright` -> `0 errors, 0 warnings, 0 informations`
  - Runtime probe output:
    - `ClaudeConnection: issubclass=True`
    - `ClaudeConnection: instantiate=ClaudeConnection`
    - `CodexConnection: issubclass=True`
    - `CodexConnection: instantiate=CodexConnection`
    - `OpenCodeConnection: issubclass=True`
    - `OpenCodeConnection: instantiate=OpenCodeConnection`

Notes:
- The shared `HarnessConnection[SpecT]` generic surface type-checks cleanly through pyright for the full connections package.
- All three concrete connections instantiate directly, so there is no residual abstract-method gap at runtime.

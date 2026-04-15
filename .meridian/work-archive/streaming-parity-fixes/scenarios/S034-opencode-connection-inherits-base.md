# S034: `OpenCodeConnection` inherits `HarnessConnection`

- **Source:** design/edge-cases.md E34 + p1411 finding M8
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @verifier (+ @unit-tester for pyright)
- **Status:** verified

## Given
The v2 design declares `class HarnessConnection(Generic[SpecT], ABC):` with abstract methods defining the lifecycle/sender/receiver contract.

## When
The runtime imports `meridian.lib.harness.connections.opencode_http` and pyright type-checks the file.

## Then
- `OpenCodeConnection` is declared as `class OpenCodeConnection(HarnessConnection[OpenCodeLaunchSpec]):` (with the explicit base and type parameter).
- `OpenCodeConnection.__bases__` includes `HarnessConnection`.
- `OpenCodeConnection.__mro__` contains `HarnessConnection`.
- Every abstract method from `HarnessConnection` is implemented; missing one raises `TypeError` on instantiation.
- Pyright reports zero errors for the file.
- The v1 `class OpenCodeConnection:` (no base) is a pattern that pyright now rejects.

## Verification
- Unit test: `assert issubclass(OpenCodeConnection, HarnessConnection)`.
- Unit test: `assert HarnessConnection in OpenCodeConnection.__mro__`.
- Unit test: try to instantiate a subclass missing one abstract method; assert `TypeError`.
- `uv run pyright src/meridian/lib/harness/connections/opencode_http.py` returns zero errors.
- Grep assertion: `rg "^class OpenCodeConnection:" src/` returns zero matches.

## Result (filled by tester)
Verified with extra coverage on 2026-04-10.

- `tests/harness/test_opencode_http.py:229` asserts `issubclass(OpenCodeConnection, HarnessConnection)` and `HarnessConnection in OpenCodeConnection.__mro__`.
- `tests/harness/test_opencode_http.py:234` adds a stronger generic-binding assertion via `OpenCodeConnection.__orig_bases__`, confirming the explicit base is `HarnessConnection[OpenCodeLaunchSpec]`.
- `tests/harness/test_opencode_http.py:245` instantiates a subclass missing one abstract method (`send_cancel`) and confirms `TypeError` is raised.
- `src/meridian/lib/harness/connections/opencode_http.py:46` declares `class OpenCodeConnection(HarnessConnection[OpenCodeLaunchSpec]):`.
- `uv run pyright` returned `0 errors, 0 warnings, 0 informations`.

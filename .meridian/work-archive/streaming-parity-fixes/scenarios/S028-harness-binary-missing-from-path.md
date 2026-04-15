# S028: Harness binary missing from PATH

- **Source:** design/edge-cases.md E28
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @smoke-tester
- **Status:** verified

## Given
Harness binary is unavailable on PATH.

## When
Spawn is launched via subprocess and streaming runners.

## Then
- Both runners surface structured `HarnessBinaryNotFound`.
- Error payload names missing binary and searched PATH.
- Error semantics are parity-aligned across runners.

## Verification
- Smoke matrix over harnesses and runner paths.
- Assert shared error class/shape and parity semantics.

## Result (filled by tester)

**verified** — @smoke-tester p1491 on claude-opus-4-6 (2026-04-11)

### Matrix — 3 harnesses × 2 runners, all 6 cells OK

Driver: `/tmp/smoke-p1491-out/s028_smoke.py` (overrides `PATH=/tmp/nonexistent-phase8:/tmp`, imports real library paths, invokes `spawn_and_stream` and `run_streaming_spawn` directly — no synthetic stub).

| Harness  | Runner     | Class                  | `harness_id` | `binary_name` | `searched_path` (prefix) |
|----------|------------|------------------------|--------------|---------------|--------------------------|
| claude   | subprocess | `HarnessBinaryNotFound`| `claude`     | `claude`      | `/tmp/nonexistent-phase8:/tmp` |
| claude   | streaming  | `HarnessBinaryNotFound`| `claude`     | `claude`      | `/tmp/nonexistent-phase8:/tmp` |
| codex    | subprocess | `HarnessBinaryNotFound`| `codex`      | `codex`       | `/tmp/nonexistent-phase8:/tmp` |
| codex    | streaming  | `HarnessBinaryNotFound`| `codex`      | `codex`       | `/tmp/nonexistent-phase8:/tmp` |
| opencode | subprocess | `HarnessBinaryNotFound`| `opencode`   | `opencode`    | `/tmp/nonexistent-phase8:/tmp` |
| opencode | streaming  | `HarnessBinaryNotFound`| `opencode`   | `opencode`    | `/tmp/nonexistent-phase8:/tmp` |

- Structured dataclass fields populated and accessible (pre-Phase 8 `FrozenInstanceError` regression is gone).
- Error class/shape is parity-aligned across runners: both paths raise the *same* `HarnessBinaryNotFound` subclass with identical field schema.
- Unit test `tests/exec/test_streaming_runner.py::test_run_streaming_spawn_raises_structured_missing_binary_error` ✅ passes.
- Raw run log: `/tmp/smoke-p1491-out/s028_smoke.py` + `bash` invocation, all 6 cells print `[OK]`.

Gate: `uv run ruff check .` → `All checks passed!`

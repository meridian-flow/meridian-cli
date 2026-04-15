# Phase 2: SpawnExtractor Protocol and Streaming Session Surface

**Risk:** Low  
**Design docs:** [overview.md](../design/overview.md), [streaming-runner.md](../design/streaming-runner.md)

## Scope

Introduce the extraction boundary that lets streaming-backed spawns reuse the same finalization pipeline as subprocess-backed spawns. This phase is preparatory only: no routing changes and no new execution path.

## Files to Modify

- `src/meridian/lib/launch/extract.py`
  Change `enrich_finalize()` to depend on a `SpawnExtractor` protocol rather than `SubprocessHarness`.
- `src/meridian/lib/harness/adapter.py`
  Define the shared extraction protocol in a location both subprocess adapters and streaming extraction code can satisfy structurally.
- `src/meridian/lib/harness/connections/base.py`
  Add `session_id` to the `HarnessConnection` protocol.
- `src/meridian/lib/harness/connections/codex_ws.py`
  Expose the existing thread/session identity through the new property.
- `src/meridian/lib/harness/connections/opencode_http.py`
  Expose the existing session identity through the new property.
- `src/meridian/lib/harness/connections/claude_ws.py`
  Expose the session identity once observed from the stream/handshake.
- `src/meridian/lib/harness/common.py`
  Make `output.jsonl` readers envelope-aware with a shared unwrapping helper so extraction works for both legacy raw lines and streaming envelopes.
- `src/meridian/lib/launch/report.py`
  Use the extractor protocol instead of a concrete adapter when reading fallback report content.
- `src/meridian/lib/launch/session_ids.py`
  Use the extractor protocol instead of a concrete adapter when extracting a session id.
- `tests/harness/test_extraction.py`
  Extend tests to cover streaming envelope format in `output.jsonl`.

## Dependencies

- Requires: none
- Produces: protocol-compatible finalization inputs for the future streaming runner
- Independent of: manager lifecycle handoff, config split

## Interface Contract

```python
@runtime_checkable
class SpawnExtractor(Protocol):
    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage: ...
    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...
    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...
```

And on connections:

```python
class HarnessConnection(Protocol):
    @property
    def session_id(self) -> str | None: ...
```

The subprocess adapters should satisfy `SpawnExtractor` without behavior changes. The streaming path can add `StreamingExtractor` in the runner phase or here if that produces cleaner diffs.

## Patterns to Follow

- Reuse the JSONL extraction helpers already centralized in `src/meridian/lib/harness/common.py`.
- Preserve the current adapter-specific parsing behavior; this phase is about dependency inversion, not new extraction heuristics.

## Constraints and Boundaries

- Do not add `streaming_runner.py` yet.
- Do not change `execute.py` routing yet.
- Keep the old subprocess path behavior identical aside from accepting streaming envelopes in shared extractors.

## Verification Criteria

- `uv run pytest tests/harness/test_extraction.py` passes.
- Existing report/session extraction tests still pass for raw subprocess artifacts.
- `uv run pyright` passes.

## Staffing

- Builder: `@coder`
- Testers: `@verifier`

## Completion Signal

This phase is done when `enrich_finalize()` can work against either a subprocess adapter or a streaming-backed extractor without knowing which path produced the artifacts.

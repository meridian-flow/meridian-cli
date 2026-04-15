# Phase 2: SpawnExtractor Protocol and Streaming Session Surface

## Goal

Introduce a `SpawnExtractor` protocol that decouples artifact extraction from `SubprocessHarness`, and add `session_id` property to `HarnessConnection`. Make extraction functions work with both subprocess and (future) streaming-backed extractors. Add envelope-aware unwrapping to shared extraction helpers.

This is a no-behavior-change refactor — the subprocess path continues to work identically, but the extraction interface is now protocol-based.

## Changes Required

### 1. `src/meridian/lib/harness/adapter.py`

Add a new `SpawnExtractor` protocol with the 3 extraction methods extracted from `SubprocessHarness`:

```python
@runtime_checkable
class SpawnExtractor(Protocol):
    """Artifact extraction interface for spawn finalization."""
    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage: ...
    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...
    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...
```

`SubprocessHarness` already has these 3 methods so it implicitly satisfies `SpawnExtractor` — do NOT change `SubprocessHarness`.

### 2. `src/meridian/lib/harness/connections/base.py`

Add `session_id: str | None` as a property on `HarnessConnection`:

```python
@runtime_checkable
class HarnessConnection(HarnessLifecycle, HarnessSender, HarnessReceiver, Protocol):
    @property
    def harness_id(self) -> HarnessId: ...
    @property
    def spawn_id(self) -> SpawnId: ...
    @property
    def capabilities(self) -> ConnectionCapabilities: ...
    @property
    def session_id(self) -> str | None: ...
```

### 3. Connection implementations

**`src/meridian/lib/harness/connections/codex_ws.py`**: Add `session_id` property that returns `self._thread_id`.

**`src/meridian/lib/harness/connections/claude_ws.py`**: Add `session_id` property. Claude doesn't track session_id in the connection currently, so return `None` for now (the subprocess extraction fallback will handle it).

**`src/meridian/lib/harness/connections/opencode_http.py`**: Add `session_id` property that returns `self._session_id` (already tracked internally).

### 4. `src/meridian/lib/launch/extract.py`

Change `enrich_finalize()` signature from `adapter: SubprocessHarness` to `extractor: SpawnExtractor`:

```python
def enrich_finalize(
    *,
    artifacts: ArtifactStore,
    extractor: SpawnExtractor,  # was: adapter: SubprocessHarness
    spawn_id: SpawnId,
    log_dir: Path,
    secrets: tuple[SecretSpec, ...] = (),
) -> FinalizeExtraction:
```

Update the body to use `extractor.extract_usage()`, `extractor.extract_session_id()`, `extractor.extract_report()`.

Import `SpawnExtractor` from `meridian.lib.harness.adapter` instead of (or in addition to) `SubprocessHarness`.

### 5. `src/meridian/lib/launch/report.py`

Change `extract_or_fallback_report()` parameter from `adapter: SubprocessHarness | None` to `extractor: SpawnExtractor | None`:

```python
def extract_or_fallback_report(
    artifacts: ArtifactStore,
    spawn_id: SpawnId,
    *,
    extractor: SpawnExtractor | None = None,  # was: adapter: SubprocessHarness | None
) -> ExtractedReport:
```

Update the body to call `extractor.extract_report()` instead of `adapter.extract_report()`.

### 6. `src/meridian/lib/launch/session_ids.py`

Change `extract_latest_session_id()` parameter from `adapter: SubprocessHarness` to `extractor: SpawnExtractor`:

```python
def extract_latest_session_id(
    *,
    extractor: SpawnExtractor,  # was: adapter: SubprocessHarness
    ...
) -> str | None:
```

Note: The `detect_primary_session_id` part of this function uses `SubprocessHarness` methods not on `SpawnExtractor`. Keep it working: if the extractor is also a `SubprocessHarness` (check with isinstance), call `detect_primary_session_id`. Otherwise, skip that detection path.

### 7. `src/meridian/lib/harness/common.py`

Add an `unwrap_event_payload()` helper:

```python
def unwrap_event_payload(line: dict[str, object]) -> dict[str, object]:
    """Extract the effective payload from an output.jsonl line.
    
    Handles both envelope format (streaming drain) and raw format (legacy).
    """
    if "event_type" in line and "payload" in line:
        payload = line["payload"]
        if isinstance(payload, dict):
            return cast("dict[str, object]", payload)
    return line
```

Update `_iter_json_lines_artifact()` to use this unwrap helper, so all extraction that parses `output.jsonl` becomes envelope-aware.

### 8. `src/meridian/lib/launch/runner.py`

Update calls to `enrich_finalize()` and `extract_latest_session_id()` to pass `extractor=adapter` instead of `adapter=adapter`. The adapter still satisfies the protocol — this is just a parameter rename.

### 9. `tests/harness/test_extraction.py`

Add test cases for:
- `unwrap_event_payload()` with envelope format returns inner payload
- `unwrap_event_payload()` with raw format returns the line as-is
- Extraction functions work correctly with envelope-wrapped output.jsonl lines

### 10. Update any other callers

Search for all callers of `enrich_finalize`, `extract_or_fallback_report`, and `extract_latest_session_id` to ensure they pass the renamed parameter.

## Files to Read First

- `src/meridian/lib/harness/adapter.py` (SpawnExtractor protocol location)
- `src/meridian/lib/harness/connections/base.py` (session_id property)
- `src/meridian/lib/launch/extract.py` (enrich_finalize)
- `src/meridian/lib/launch/report.py` (extract_or_fallback_report)
- `src/meridian/lib/launch/session_ids.py` (extract_latest_session_id)
- `src/meridian/lib/harness/common.py` (unwrap helper)
- `src/meridian/lib/launch/runner.py` (caller)
- `src/meridian/lib/harness/connections/codex_ws.py`
- `src/meridian/lib/harness/connections/claude_ws.py`
- `src/meridian/lib/harness/connections/opencode_http.py`
- `tests/harness/test_extraction.py`

## Verification

- `uv run pytest tests/harness/test_extraction.py -x` passes
- `uv run pytest tests/ -x` passes (full suite to catch callers)
- `uv run pyright` passes (0 errors)
- `uv run ruff check .` passes

# Slice: Move extraction into launch/

## Goal
Move the extraction code from `src/meridian/lib/extract/` into `src/meridian/lib/launch/`.

## Work

### 1. Create launch/extract.py
- Read `src/meridian/lib/extract/finalize.py` — finalization logic (note: `_io.py` was already merged into this in Phase 1)
- Move to `src/meridian/lib/launch/extract.py`
- Replace `extract/finalize.py` with re-export shim from `meridian.lib.launch.extract`

### 2. Create launch/report.py
- Read `src/meridian/lib/extract/report.py` — report extraction
- Move to `src/meridian/lib/launch/report.py`
- Replace `extract/report.py` with re-export shim from `meridian.lib.launch.report`

### 3. Create launch/files_touched.py
- Read `src/meridian/lib/extract/files_touched.py` — file change detection
- Move to `src/meridian/lib/launch/files_touched.py`
- Replace `extract/files_touched.py` with re-export shim from `meridian.lib.launch.files_touched`

### 4. Update extract/__init__.py
- Update to re-export from new launch locations if it currently exports anything

### 5. Update extract/_io.py shim
- `_io.py` was already made into a shim/compat module in Phase 1 pointing to `extract/finalize.py`. Now that finalize.py itself is a shim to `launch/extract.py`, check that the chain works (shim → shim → real code). If it causes issues, update `_io.py` to point directly to `meridian.lib.launch.extract`.

## Rules
- Read every file before modifying
- Leave re-export shims at ALL old paths
- Do NOT update imports in files outside the extract/ package
- Do NOT add any new tests
- No behavior changes

## Verification
Run `uv run pytest-llm` and `uv run pyright` — both must pass.

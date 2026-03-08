# Slice: Move prompt assembly into launch/

## Goal
Move the prompt assembly code from `src/meridian/lib/prompt/` into `src/meridian/lib/launch/`.

## Work

### 1. Create launch/prompt.py
- Read `src/meridian/lib/prompt/compose.py` — main prompt composition
- Read `src/meridian/lib/prompt/assembly.py` — prompt assembly helpers
- Read `src/meridian/lib/prompt/sanitize.py` — prompt sanitization
- Merge all three into `src/meridian/lib/launch/prompt.py`
- Resolve cross-imports between the three files (they become local references)
- Replace each original file with a re-export shim from `meridian.lib.launch.prompt`

### 2. Create launch/reference.py
- Read `src/meridian/lib/prompt/reference.py` — reference file handling
- Move to `src/meridian/lib/launch/reference.py`
- Replace `prompt/reference.py` with re-export shim from `meridian.lib.launch.reference`

### 3. Update prompt/__init__.py
- Read `src/meridian/lib/prompt/__init__.py`
- Update it to re-export from the new launch locations (if it currently exports anything)

## Rules
- Read every file before modifying
- Leave re-export shims at ALL old paths
- Do NOT update imports in files outside the prompt/ package
- Do NOT add any new tests
- No behavior changes

## Verification
Run `uv run pytest-llm` and `uv run pyright` — both must pass.

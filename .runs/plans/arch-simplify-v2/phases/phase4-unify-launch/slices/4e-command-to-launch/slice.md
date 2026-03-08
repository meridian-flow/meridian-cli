# Slice: Move primary launch command building into launch/

## Goal
Move the space launch command and process modules into `src/meridian/lib/launch/`.

## Work

### 1. Create launch/command.py (from space/_launch_command.py)
- Read `src/meridian/lib/space/_launch_command.py` — build harness CLI command
- Move to `src/meridian/lib/launch/command.py`
- Update internal imports: this file likely imports from other `space/_launch_*` files that have already moved to `launch/`. Update those to use `launch/` relative imports.
- Replace `space/_launch_command.py` with re-export shim

### 2. Create launch/process.py (from space/_launch_process.py)
- Read `src/meridian/lib/space/_launch_process.py` — fork/exec + stream + finalize
- Move to `src/meridian/lib/launch/process.py`
- Update internal imports: this file likely imports from other `space/_launch_*` files and `exec/` files that have moved to `launch/`. Update to use `launch/` relative imports.
- Replace `space/_launch_process.py` with re-export shim

### 3. Thin out space/launch.py
- Read `src/meridian/lib/space/launch.py` — the current public facade
- This file should remain as a thin public entry point, but update its internal imports to use `launch/` package instead of `space/_launch_*` private modules
- Keep the same public API surface

## Rules
- Read every file before modifying
- Leave re-export shims at old paths for _launch_command.py and _launch_process.py
- Do NOT update imports in files outside space/ (other than the new launch/ files)
- Do NOT add any new tests
- space/launch.py remains as the public facade — do NOT replace it with a shim
- No behavior changes

## Verification
Run `uv run pytest-llm` and `uv run pyright` — both must pass.

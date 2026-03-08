# Slice: Move execution into launch/

## Goal
Move the subprocess execution code from `src/meridian/lib/exec/` into `src/meridian/lib/launch/`.

## Work

### 1. Create launch/runner.py (from exec/spawn.py)
- Read `src/meridian/lib/exec/spawn.py` — the main spawn execution logic
- Move to `src/meridian/lib/launch/runner.py`
- Replace `exec/spawn.py` with re-export shim

### 2. Create launch/signals.py (from exec/signals.py)
- Read `src/meridian/lib/exec/signals.py` — signal forwarding (note: process_groups.py was already merged into this in Phase 1)
- Move to `src/meridian/lib/launch/signals.py`
- Replace `exec/signals.py` with re-export shim

### 3. Create launch/env.py (from exec/env.py)
- Read `src/meridian/lib/exec/env.py` — child process environment
- Move to `src/meridian/lib/launch/env.py`
- Replace `exec/env.py` with re-export shim

### 4. Create launch/errors.py (from exec/errors.py)
- Read `src/meridian/lib/exec/errors.py` — error classification and retry
- Move to `src/meridian/lib/launch/errors.py`
- Replace `exec/errors.py` with re-export shim

### 5. Create launch/timeout.py (from exec/timeout.py)
- Read `src/meridian/lib/exec/timeout.py` — spawn timeout management
- Move to `src/meridian/lib/launch/timeout.py`
- Replace `exec/timeout.py` with re-export shim

### 6. Create launch/terminal.py (from exec/terminal.py)
- Read `src/meridian/lib/exec/terminal.py` — TTY detection
- Move to `src/meridian/lib/launch/terminal.py`
- Replace `exec/terminal.py` with re-export shim

### 7. Update exec/__init__.py
- Update to re-export from new launch locations if it currently exports anything

### 8. Fix exec/process_groups.py shim chain
- `process_groups.py` was already made into a shim pointing to `exec/signals.py` in Phase 1. Now that `signals.py` is a shim to `launch/signals.py`, verify the chain works. If not, point `process_groups.py` directly to `meridian.lib.launch.signals`.

## Rules
- Read every file before modifying
- Leave re-export shims at ALL old paths
- Do NOT update imports in files outside the exec/ package
- Do NOT add any new tests
- When moving files, update any cross-imports between exec/ files to use launch/ relative imports (since they'll all be in launch/ now)
- No behavior changes

## Verification
Run `uv run pytest-llm` and `uv run pyright` — both must pass.

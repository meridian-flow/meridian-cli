# Slice: Create launch/ scaffold with types and resolution

## Goal
Create `src/meridian/lib/launch/` package with the first two modules: types and resolution.

## Work

### 1. Create launch/__init__.py
- Create `src/meridian/lib/launch/__init__.py` (empty or minimal)

### 2. Create launch/types.py from space/_launch_types.py
- Read `src/meridian/lib/space/_launch_types.py` (~86 lines) — request/result types used by the launch stack
- Move to `src/meridian/lib/launch/types.py`
- Replace `space/_launch_types.py` with re-export shim
- **NOTE:** `harness/launch_types.py` stays in `harness/` — do NOT move it. It contains `PromptPolicy` and `SessionSeed` which are consumed by harness adapters.

### 3. Create launch/resolve.py from launch_resolve.py + space/_launch_resolve.py
- Read `src/meridian/lib/launch_resolve.py` — top-level launch resolution
- Read `src/meridian/lib/space/_launch_resolve.py` — space-specific launch resolution
- Merge both into `src/meridian/lib/launch/resolve.py`
- When merging, resolve cross-imports between the two files (they become local)
- Replace `lib/launch_resolve.py` with re-export shim from `meridian.lib.launch.resolve`
- Replace `space/_launch_resolve.py` with re-export shim from `meridian.lib.launch.resolve`

## Rules
- Read every file before modifying
- Leave re-export shims at ALL old paths
- Do NOT update imports in other files
- Do NOT add tests
- No behavior changes

## Verification
Run `uv run pytest-llm` and `uv run pyright` — both must pass.

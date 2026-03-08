# Slice: Move space stores into lib/state/

## Goal
Move `space/space_file.py` and `space/session_store.py` into `lib/state/` alongside the other file-backed stores.

## Prerequisites
The materialization cleanup dependency in `session_store.py` has already been extracted (previous slice).

## Work
1. Move `src/meridian/lib/space/space_file.py` → `src/meridian/lib/state/space_store.py`
   - Read the source file first
   - Copy content to new location
   - Replace original with re-export shim:
     ```python
     """Compatibility shim — real code lives in meridian.lib.state.space_store."""
     from meridian.lib.state.space_store import *  # noqa: F401,F403
     ```

2. Move `src/meridian/lib/space/session_store.py` → `src/meridian/lib/state/session_store.py`
   - Read the source file first  
   - Copy content to new location
   - Replace original with re-export shim:
     ```python
     """Compatibility shim — real code lives in meridian.lib.state.session_store."""
     from meridian.lib.state.session_store import *  # noqa: F401,F403
     ```

3. Update internal imports within the moved files if they reference sibling `space/` modules that haven't moved

## Rules
- Read every file before modifying
- Leave re-export shims at old paths
- Do NOT update imports in files outside the moved files — shims handle compatibility
- No behavior changes

## Verification
Run `uv run pytest-llm` and `uv run pyright` — both must pass.

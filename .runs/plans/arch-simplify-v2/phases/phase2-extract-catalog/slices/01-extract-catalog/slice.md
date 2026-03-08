# Slice: Extract catalog/ from config/

## Goal
Create a new `src/meridian/lib/catalog/` package that owns all agent/skill/model discovery and parsing code. Move it out of `config/` which should only contain application settings.

## Step 1: Create catalog/agent.py
- Read `src/meridian/lib/config/agent.py` (~285 lines) — agent profile parsing
- Move it to `src/meridian/lib/catalog/agent.py`
- Replace `config/agent.py` with a re-export shim:
  ```python
  """Compatibility shim — real code lives in meridian.lib.catalog.agent."""
  from meridian.lib.catalog.agent import *  # noqa: F401,F403
  ```
- Update internal imports within the moved file: any `from meridian.lib.config.X` imports for things that are NOT moving (like settings) should stay as-is. Any imports for things that ARE moving to catalog should be updated to the new path.

## Step 2: Create catalog/skill.py
- Read `src/meridian/lib/config/skill.py` — skill parsing
- Read `src/meridian/lib/config/skill_registry.py` — skill registry
- Merge both into `src/meridian/lib/catalog/skill.py`
- Replace `config/skill.py` with re-export shim from `meridian.lib.catalog.skill`
- Replace `config/skill_registry.py` with re-export shim from `meridian.lib.catalog.skill`

## Step 3: Create catalog/models.py
- Read `src/meridian/lib/config/aliases.py` — model aliases
- Read `src/meridian/lib/config/discovery.py` — model discovery
- Read `src/meridian/lib/config/routing.py` — model routing
- Read `src/meridian/lib/config/catalog.py` — model catalog
- Merge all four into `src/meridian/lib/catalog/models.py`
- Replace each original with a re-export shim from `meridian.lib.catalog.models`

**Important for the merge**: These 4 files may import from each other. When merging, resolve those cross-imports — they become local references within the single file. Keep the logical sections clearly separated with comment headers.

## Step 4: Absorb config/_paths.py into config/settings.py
- Read `src/meridian/lib/config/_paths.py` — path configuration
- Read `src/meridian/lib/config/settings.py` — MeridianConfig
- Move content from `_paths.py` into `settings.py`
- Replace `_paths.py` with re-export shim from `meridian.lib.config.settings`

## Step 5: Create catalog/__init__.py
- Create `src/meridian/lib/catalog/__init__.py` (can be empty or minimal)

## Rules
- Read EVERY source file before modifying it
- Leave re-export shims at ALL old paths
- Do NOT update imports in files OUTSIDE of the catalog package and the files being merged — shims handle compatibility
- Within the merged files, DO update cross-references between the merged files (e.g., if `aliases.py` imports from `discovery.py`, that becomes a local reference in `catalog/models.py`)
- Preserve ALL content, docstrings, comments
- No behavior changes — pure structural move + merge

## Verification
Run `uv run pytest-llm` and `uv run pyright` — both must pass.

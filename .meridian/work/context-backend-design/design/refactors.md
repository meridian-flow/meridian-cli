# Context Backend Refactor Agenda

## REF-CTX-001: Extract Path Resolution from StatePaths

**Current state**: `StatePaths.from_root_dir()` hardcodes `fs_dir = root_dir / "fs"` and `work_dir = root_dir / "work"`.

**Target state**: Path resolution delegates to context resolver when config is present, falls back to hardcoded paths when absent.

**Approach**: 
1. Create `resolve_context()` function that takes repo_root + config
2. Modify `resolve_repo_state_paths()` to accept optional `ContextConfig`
3. When config absent, behavior unchanged
4. When config present, use resolved paths from config

**Risk**: Low — additive change with fallback to current behavior.

---

## REF-CTX-002: Unify Environment Variable Normalization

**Current state**: `_normalize_meridian_fs_dir()` and `_normalize_meridian_work_dir()` in `env.py` resolve paths independently using `resolve_repo_state_paths()`.

**Target state**: Both functions use the same context resolver, ensuring config-based paths are consistent.

**Approach**:
1. Create `resolve_spawn_context()` that returns both paths
2. Modify `_normalize_meridian_env()` to call resolver once
3. Both env vars set from same resolution

**Risk**: Low — consolidation of existing logic.

---

## REF-CTX-003: Add Context Section to Config Loader

**Current state**: `settings.py` parses `[defaults]`, `[timeouts]`, `[harness]`, `[primary]`, `[output]` sections.

**Target state**: Add `[context]` section parsing with `work` and `fs` sub-tables.

**Approach**:
1. Add `ContextConfig` to `MeridianConfig` model
2. Extend `_normalize_toml_payload()` to handle `[context]` section
3. Add validation for path spec format

**Risk**: Low — additive to existing config infrastructure.

---

## REF-CTX-004: Create context Module

**Current state**: No `src/meridian/lib/context/` directory.

**Target state**: New module with:
- `resolver.py` — path resolution logic
- `git_sync.py` — git sync operations
- `__init__.py` — public exports

**Risk**: None — new code.

---

## REF-CTX-005: Add Context CLI Command Group

**Current state**: No `meridian context` command.

**Target state**: New command group with `show`, `sync`, `migrate` subcommands.

**Approach**:
1. Create `context_cmd.py` with click group
2. Register in `main.py` command tree
3. Wire to ops functions

**Risk**: None — new code.

---

## Sequencing

1. **REF-CTX-003** (config schema) — no dependencies, enables all else
2. **REF-CTX-004** (context module) — no dependencies, pure addition
3. **REF-CTX-001** (path resolution) — depends on 003, 004
4. **REF-CTX-002** (env normalization) — depends on 001
5. **REF-CTX-005** (CLI) — depends on 001, 004

Phases 1-2 can parallelize. Phases 3-5 are sequential.

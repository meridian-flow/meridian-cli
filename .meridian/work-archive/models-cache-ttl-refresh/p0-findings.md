# P0 Dead-Code Sweep Findings (from p1014 / refactor-reviewer / gpt-5.4)

In-scope files reviewed:
- `../mars-agents/src/models/mod.rs`
- `../mars-agents/src/cli/models.rs`
- `../mars-agents/src/cli/sync.rs`
- `../mars-agents/src/sync/mod.rs`
- `src/meridian/lib/catalog/model_aliases.py`
- `src/meridian/lib/catalog/models.py`

## Findings

| ID | Status | Location | Symbol | Justification |
|----|--------|----------|--------|---------------|
| F1 | SAFE | `src/meridian/lib/catalog/models.py:45-51` + `__all__` export at :565 | `resolve_alias` | Workspace-wide rg finds no callers beyond its own `__all__` export string. |
| F2 | SAFE | `src/meridian/lib/catalog/model_aliases.py:363-370` | `merge_alias_entries` | No production call sites; only referenced by `tests/lib/catalog/test_model_aliases.py`. |
| F3 | SAFE | `src/meridian/lib/catalog/model_aliases.py:373-380` | `load_alias_by_name` | Only production caller is `resolve_alias` in `models.py` (itself F1, unused). All remaining references are test-only. |
| F4 | AMBIGUOUS | `../mars-agents/src/sync/mod.rs:95-99` (`ResolvedState.model_aliases`) and `:246-251` (`merge_model_config(...)`) | Stored field never read anywhere, but the computation still emits alias-conflict diagnostics. Deferring decision. |

## Notes
- Mars-agents Rust files (`models/mod.rs`, `cli/models.rs`, `cli/sync.rs`) had no clean deletion candidates — phase 2/3/4 will fully rewrite the relevant sections, so the surface stays as-is for now.
- Tests that exercise F1/F2/F3 will need to be deleted alongside the production helpers (cascading deletion of dead test code).

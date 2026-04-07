# Plan Overview — Models Cache TTL Refresh

Seven phases, ordered so each can be smoke-tested independently. Phase 0
is a scoped dead-code sweep on the files Phases 1-6 will touch. Phases
1-5 all live in the `mars-agents` repo (`../mars-agents/`). Phase 6 is
the meridian-channel follow-up.

| Phase | Title                                    | Repo            | Depends on |
|-------|------------------------------------------|-----------------|------------|
| 0     | Scoped dead-code sweep (baseline)        | both            | —          |
| 1     | Config: `models_cache_ttl_hours`         | mars-agents     | 0          |
| 2     | `ensure_fresh` helper + lock integration | mars-agents     | 1          |
| 3     | Wire `mars models` commands              | mars-agents     | 2          |
| 4     | Wire `mars sync`                         | mars-agents     | 2          |
| 5     | Mars-side tests (unit + smoke)           | mars-agents     | 3, 4       |
| 6     | Meridian integration + smoke test        | meridian-channel| 5          |

Phase 0 produces a clean baseline on the exact files Phases 1-6 edit
(`src/models/mod.rs`, `src/cli/models.rs`, `src/cli/sync.rs`,
`src/sync/mod.rs`, `src/meridian/lib/catalog/model_aliases.py`,
`src/meridian/lib/catalog/models.py`) so the feature diffs aren't
muddied by refactor noise. It is deletions-only — see
`phase-0-dead-code-sweep.md`. Phases 3 and 4 are independent of each
other and can run in parallel after phase 2 lands — both depend only on
`ensure_fresh` existing. Phase 5 waits for both because the unit tests
cover both call-site groups, but the smoke test can begin as soon as
either phase 3 or 4 is in.

## Parallelization Map

```
P0 ─> P1 ─> P2 ─┬─> P3 ─┐
                └─> P4 ─┼─> P5 ─> P6
                       /
```

Agents should serialize P0→P1→P2, then fan out P3 and P4 as two
concurrent coder spawns, then join on P5 and hand off to P6. P0 must
fully converge (deletions landed, reviewers clean) before P1 begins —
the whole point is that P1+ diffs read against the cleaned baseline.

## Cross-Phase Artifacts

- **`ensure_fresh` signature** (phase 2) is load-bearing for phases 3, 4,
  5 — if the signature changes mid-plan, all three downstream phases need
  to re-verify. Any coder touching phase 2 must ping the orchestrator
  before deviating from `design/ensure-fresh.md`.
- **`SyncOptions.no_refresh_models`** (phase 4) and
  **`ListArgs.no_refresh_models` / `ResolveAliasArgs.no_refresh_models`**
  (phase 3) are independent additions to separate structs; they don't
  conflict.
- **Shared helpers `resolve_refresh_mode` and `load_models_cache_ttl`**
  are introduced in phase 2 alongside `ensure_fresh` so both phase 3 and
  phase 4 can import them from the same module without a merge hazard.

## Success Criteria (from requirements.md)

Each phase's blueprint ends with a verification list that rolls up into
the overall success criteria:

1. `meridian mars add <pkg> && meridian mars sync --force` followed by a
   spawn using a new alias just works.
2. `meridian mars add` + immediate spawn (no sync) works.
3. `MARS_OFFLINE=1 meridian mars sync` never hits the network; spawning a
   new alias afterward fails with a clean actionable error.
4. TTL is configurable in mars.toml; default is 24 hours.
5. Concurrent spawns do not produce duplicate network fetches.

Phase 5 and 6 together exercise all five.

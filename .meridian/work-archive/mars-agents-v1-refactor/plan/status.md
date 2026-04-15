# Implementation Status

## Execution Rounds

```
Round 1: Phase 1, Phase 2, Phase 3     (independent — can run in parallel)
Round 2: Phase 4                        (requires Phase 3 for error variants)
Round 3: Phase 5, Phase 6              (Phase 5 requires Phase 4; Phase 6 benefits from Phase 4)
Round 4: Phase 7                        (requires Phase 6 + Phase 2)
Round 5: Phase 8                        (requires all prior)
```

## Phase Status

| Phase | Description | Status | Spawn |
|-------|-------------|--------|-------|
| 1 | Frontmatter module | not started | — |
| 2 | Source spec parser | not started | — |
| 3 | Exit code mapping | not started | — |
| 4 | Unified sync pipeline | not started | — |
| 5 | Resolver locked SHA | not started | — |
| 6 | Foundation newtypes | not started | — |
| 7 | Path newtypes + SourceId | not started | — |
| 8 | Cleanup | not started | — |

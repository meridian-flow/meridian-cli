# Implementation Status

## Execution Rounds

```
Round 1: Phase 1, Phase 2     (Phase 2 depends on Phase 1 types but can overlap)
Round 2: Phase 3               (needs both Phase 1 + 2)
Round 3: Phase 4               (needs Phase 3)
```

## Phase Status

| Phase | Description | Status | Spawn |
|-------|-------------|--------|-------|
| 1 | Dependencies, error variants, type changes | not started | — |
| 2 | URL normalization — preserve scheme | not started | — |
| 3 | Implement fetch — archive + system git | not started | — |
| 4 | Global cache + repair fix + cleanup | not started | — |

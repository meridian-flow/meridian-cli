# Backlog Execution Archive (2026-03-03)

Execution source: `plans/backlog-execution.md`  
Execution anomalies/workarounds: `plans/backlog-execution-anomalies.md`

## Closed Items

| ID | Category | Resolution | Commit(s) |
|----|----------|------------|-----------|
| BUG-1 | Bugs | PID-based orphan detection + doctor repair alignment | `b9d1f5f` |
| BUG-3 | Bugs | Token usage defaults changed from `0/0` to nullable fields | `771bc17` |
| BUG-4 | Bugs | Path extraction tightened to avoid pseudo-path false positives | `5e7cba6` |
| BUG-5 | Bugs | Timeout/cancel failure markers + structured empty-output artifacts | `c250e50`, `70d1f3f` |
| BUG-6 | Bugs | Claude/OpenCode switched to stdin prompt marker to avoid `E2BIG` | `6fcc6be` |
| IMP-1 | Improvements | Failure summary now tags timeout/cancel cases | `c250e50` |
| IMP-2 | Improvements | Stderr verbosity tiers implemented in terminal output path | `2daf83f` |
| IMP-3 | Improvements | `spawn cancel` command + operation registration | `7c8fa93` |
| IMP-4 | Improvements | Wait-loop heartbeat output with verbosity-aware behavior | `980aabd` |
| IMP-5 | Improvements | Closed-space validation at spawn-create entry | `6967664` |
| IMP-6 | Improvements | User-facing terminology cleanup (`run` -> `spawn`) | `6ad3d42` |
| TD-1 | Tech Debt | Spawn execution lifecycle shared helpers/context extraction | `deaee4c` |
| TD-2 | Tech Debt | Canonical space resolver threading across spawn/reference paths | `aeb01c9` |
| TD-3 | Tech Debt | Shared `merge_warnings` utility consolidation | `ae61da7` |
| TD-4 | Tech Debt | CLI spawn plumbing tests merged into one module | `8b33a8a` |
| TD-5 | Tech Debt | Streaming/subspawn enrichment tests consolidated | `88a3429` |
| TD-6 | Tech Debt | Shared test helpers introduced and adopted broadly | `6d6fcf0` |

## Notes

- This archive records completion of the 17-item backlog execution batch.
- Legacy closed items that predated this batch remain closed:
  - `BUG-2` report overwrite behavior
  - `BUG-7` duplicate skill warnings

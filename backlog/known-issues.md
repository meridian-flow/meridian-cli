# Known Issues Backlog

Date added: 2026-03-02
Source: consolidated from `plans/backlog.md`

## Open

### Orphaned runs stay "running" forever after process kill
- Status: `todo`
- Found: `2026-03-01`
- Severity: `medium`
- Description: When a `meridian spawn` parent process is killed (or crashes), the child process can orphan and the run record remains `status: "running"` indefinitely.
- Notes: Space lock cleanup exists (`cleanup_orphaned_locks()`), but spawn/run cleanup parity is missing.
- Proposed direction: Add child PID tracking and `cleanup_orphaned_runs()` or equivalent finalization on termination signals.

### `meridian start` does not inject skills via `--append-system-prompt`
- Status: `todo`
- Found: `2026-03-01`
- Severity: `high`
- Description: Primary launch resolves skills but does not consistently inject them through the same mechanism used in spawn path.
- Related plan: `plans/unify-harness-launch.md` Step 0 and Step 1.

### Agent profiles have no default skills
- Status: `todo`
- Found: `2026-03-01`
- Severity: `medium`
- Description: Multiple agent profiles were discovered with empty `skills`, where sensible defaults are expected.
- Related plan: `plans/unify-harness-launch.md` Step 0.

### `report.md` not overwritten cleanly between runs
- Status: `todo`
- Found: `2026-03-01`
- Severity: `medium`
- Description: Report behavior can persist stale output between runs, and lookup can resolve wrong report when run IDs repeat across spaces.
- Related plan: `plans/space-plumbing-fix.md` Step 1.

### `-f @name` reference loading ignores threaded space context
- Status: `todo`
- Found: `2026-03-01`
- Severity: `medium`
- Description: Prompt reference loading reads `MERIDIAN_SPACE_ID` directly rather than using threaded/explicit operation space context.
- Related plan: `plans/space-plumbing-fix.md` Step 2.

### Artifact keys lack space component (cross-space collision risk)
- Status: `todo`
- Found: `2026-03-01`
- Severity: `medium`
- Description: Run IDs are per-space, but artifact keying can still collide when keyed only by run ID.
- Related plan: `plans/space-plumbing-fix.md` Step 3.

### Duplicate skill warnings from overlapping skill paths
- Status: `todo`
- Found: `2026-03-01`
- Severity: `low`
- Description: Overlapping local and bundled skill paths produce noisy duplicate warnings.

## Done
- Move completed items here with date and short resolution note.

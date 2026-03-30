---
name: __meridian-work-coordination
description: Meridian work lifecycle and artifact placement for orchestrators. Use this whenever you need to create, switch, update, or complete a work item, or decide where work-scoped notes versus broader shared docs belong.
---

# Work Coordination

The orchestrator owns work state — subagents should not mutate it unless explicitly instructed.

If meaningful repo work is about to start, create or attach to a work item:

```bash
meridian work start "descriptive name"   # create new
meridian work switch descriptive-name    # attach to existing
```

## Dashboard

```bash
meridian work                    # dashboard — what's in flight
meridian work list               # list active work items
meridian work list --done        # list done/archived items
meridian work show auth-refactor # drill into one work item
```

## Status Management

Status values are free-form. Keep the current phase visible:

```bash
meridian work update auth-refactor --status designing
meridian work update auth-refactor --status implementing
meridian work done auth-refactor
meridian work reopen auth-refactor
```

`work done` archives the work directory. `work reopen` restores it.

## Artifact Placement

**`$MERIDIAN_WORK_DIR`** — what you're actively working on right now. Scoped to the current work item and archived when the work completes. Examples: design docs, planning notes, implementation notes.

**`$MERIDIAN_FS_DIR`** — long-lived reference material that helps humans and agents quickly get up to speed. Persists across work items. Examples: architecture overviews, codebase guides, API conventions, onboarding context.

Rule of thumb: if it helps *this* work item, use `$MERIDIAN_WORK_DIR`. If it helps *any* task understand the project, use `$MERIDIAN_FS_DIR`.

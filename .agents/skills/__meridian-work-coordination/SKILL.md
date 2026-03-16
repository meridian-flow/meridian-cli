---
name: __meridian-work-coordination
description: Meridian work item lifecycle for tracking multi-spawn efforts. Use when creating, switching, updating, or completing work items, managing work status, or deciding where work-scoped files vs shared project files belong.
---

# Work Coordination

This skill owns Meridian work-management policy for orchestrators.

Use it to answer:

- when to run `meridian work start`, `switch`, `update`, `done`, or `clear`
- what counts as the authoritative work record
- what belongs in `$MERIDIAN_WORK_DIR`
- what belongs in `.meridian/fs/`

Subagents usually do not need this skill. They should follow the orchestrator's scoped prompt and the files they are given.

## Ownership

Work coordination is primary-owned.

- The orchestrator creates or attaches to real work items.
- The orchestrator updates work status as phases progress.
- The orchestrator decides what tracking artifacts to keep.
- Subagents should not mutate shared work state unless explicitly instructed.

If meaningful repo work is about to start and there is no active work item, create one first:

```bash
meridian work start "descriptive name"
```

If the work item already exists:

```bash
meridian work switch descriptive-name
```

## Work Model

Meridian separates work metadata from work-scoped scratch files:

- `.meridian/work-items/<slug>.json`
  - authoritative work-item metadata
  - status, description, created-at, and other Meridian-owned coordination state
- `.meridian/work/<slug>/`
  - optional work-scoped scratch/docs
  - design notes, decision logs, implementation logs, per-phase plans
- `.meridian/work-archive/<slug>/`
  - archived scratch/docs for completed work items
- `.meridian/fs/`
  - broader shared reference material not owned by one work item

The key rule is:

- `work-items` is authority
- `work` is work-scoped scratch
- `work-archive` is completed work scratch
- `fs` is broader shared reference space

## Status Management

Track progress with `meridian work update --status`:

```bash
meridian work start "auth refactor"
meridian work update auth-refactor --status "in-progress"
meridian work update auth-refactor --status "blocked"
meridian work done auth-refactor
meridian work reopen auth-refactor
```

Status values are free-form strings. Use whatever names make sense for your workflow.

Use `meridian work clear` only when you intentionally want no active work item for the current session.
`work done` archives the scratch directory when present, and `work reopen` restores it.

## Artifact Placement

When a work item is active, `$MERIDIAN_WORK_DIR` points at its work-scoped scratch directory:

```bash
echo "$MERIDIAN_WORK_DIR"
# .meridian/work/auth-refactor/
```

Your workflow skills determine what files to create in `$MERIDIAN_WORK_DIR`. This skill defines where things go, not what they are.

Use `.meridian/fs/` for broader shared reference material that is not specific to one work item, such as:

- cross-work-item reference docs
- shared architecture notes used by multiple efforts
- reusable datasets, fixtures, or reference outputs

If a file mainly exists to help one work item move forward, keep it in `$MERIDIAN_WORK_DIR`.
If it is shared project context across multiple work items, put it in `.meridian/fs/`.

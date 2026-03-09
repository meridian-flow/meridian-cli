# Meridian Coordination Layer — Design

## Problem

Operators (human or agent) have no way to see what's actively being worked on across a project. `meridian spawn list` shows spawn lifecycle (status, duration, cost) but not *intent* — what is this spawn doing, and what bigger effort is it part of?

## Design Decisions

- **Work items are a core concept.** Meridian is a coordination layer — work tracking is coordination. Opinionated, same level as spaces, spawns, reports, skills.
- **Work items are git tracked.** Valuable working documents. Visible in PRs alongside code. Delete when done; git history preserves them.
- **Work items are space-scoped.** Everything in meridian is space-scoped.
- **No locks, no claimed_files.** Coordination through visibility, not mechanisms. Agents infer boundaries from work item docs and their prompt — same way a human developer reads the plan and knows what's someone else's area. `files_touched` (already tracked per spawn) serves as after-the-fact diagnostic.
- **Single worktree.** All agents work in the same branch. Aggressive refactoring makes merges too painful.
- **Storage abstraction.** Local files today, file-backed and git-tracked. Interface should support a managed service later, but work items are file-authoritative — don't over-promise a clean backend swap.
- **`work/` is task-scoped, `fs/` is space-scoped.** Each work item directory (`work/auth-refactor/`) contains design docs, plans, and diagrams for one major task — created via `meridian work start`, lives and dies with that effort. `fs/` is space-wide reference material shared across all work items: architecture notes, team conventions, reference docs. A work item might reference stuff in `fs/`, but `fs/` doesn't belong to any particular work item.
- **Text output is the primary interface.** Both humans and agents read text. No `--format json` needed on coordination commands — agents parse text fine. JSON stays where it belongs: JSONL stores, API/adapter responses for future viewer UI.
- **Env vars use `_DIR` suffix for paths.** `MERIDIAN_SPACE_FS_DIR`, `MERIDIAN_WORK_DIR`. Consistent convention.
- **One command: `meridian work`.** Dashboard + management in one top-level command. No separate `design` namespace.

## Space Directory Layout

```
.meridian/.spaces/<space-id>/
  work/              # git tracked — structured, meridian-managed
    auth-refactor/
      work.json
      overview.md
      auth-flow.mmd
      plan/
        step-1.md
        step-2.md
  fs/               # git tracked — freeform, agent-managed
  spawns/           # gitignored — ephemeral runtime state
    p5/
      params.json   # structured metadata (model, desc, work_id, etc.)
      prompt.md     # full prompt text — separate file, not in params.json
      output.jsonl  # harness output log
      stderr.log
      report.md
  space.json        # gitignored
  spawns.jsonl      # gitignored
  sessions.jsonl    # gitignored
```

### .gitignore strategy

Ignore everything in `.meridian/` except `work/` and `fs/`:

```gitignore
# Ignore everything by default
*

# Track .gitignore itself
!.gitignore

# Track work/ and fs/ within spaces
!.spaces/
!.spaces/*/
!.spaces/*/work/
!.spaces/*/work/**
!.spaces/*/fs/
!.spaces/*/fs/**
```

## Work Items

Each work item is a directory with a `work.json` and freeform files:

```json
{
  "name": "auth-refactor",
  "description": "Extract session logic and add new middleware",
  "state": "in_progress",
  "status": "implementing step 2",
  "created_at": "2026-03-08T..."
}
```

- `state` is a stable enum: `draft`, `ready`, `in_progress`, `blocked`, `done` — scannable in dashboards
- `status` is a free-form string for context — operator sets whatever makes sense
- Can contain anything: markdown, mermaid diagrams, code snippets
- Plans live inside as `plan/` subdirectory when needed
- Work items are living documents — start rough, refine over time

### Active Work Item (per operator session)

Each operator session is associated with one work item at a time. Active work item is UX sugar, not the source of truth — `work_id` is snapshotted on each spawn at creation time.

Sets `$MERIDIAN_WORK_DIR`. Optional — spawns without a work item show up ungrouped.

## Spawn Changes

### Prompt storage

Full prompt stored as a separate file per spawn — not embedded in params.json or JSONL:

```
spawns/p5/prompt.md     # full prompt text (forensics, debugging, viewer)
spawns/p5/params.json   # structured metadata (model, desc, work_id, etc.)
```

`prompt.md` is for forensics and deep inspection. For coordination, agents use `--desc` and work item context.

### Description

Optional short label on spawn create:

```bash
meridian spawn -m opus --desc "Implement step 2" -p @prompt.md
```

### Work attachment

`work_id` is snapshotted at creation time for both primary sessions and child spawns. Not derived from ambient session state at query time — the session/spawn owns its `work_id` permanently.

- **Primary session** (`meridian start`) — captures active work item into session metadata
- **Child spawn** (`meridian spawn`) — captures into `params.json` and spawn events

No registry of active sessions in `work.json` — derive it at query time from running sessions/spawns that have `work_id` set. Single source of truth, no drift.

```bash
# Spawn inherits active work item from session
meridian work start "auth refactor"
meridian spawn -m opus -p "implement step 2"
# -> spawn gets work_id: "auth-refactor"

# Or explicit override:
meridian spawn -m opus --work auth-refactor -p "implement step 2"
```

## Commands

### `meridian work`

```bash
meridian work                                          # dashboard — what's happening now
meridian work start "auth refactor"                    # create work item + set as active
meridian work update auth-refactor --state done        # update work item
meridian work update auth-refactor --status "step 2"   # update free-form status
```

Dashboard output:

```
ACTIVE
  auth-refactor          in_progress — implementing step 2
    p5  opus     running   Implement step 2
    p6  gpt-5.4  running   Review step 1

  spawn-visibility       draft — drafting design
    p9  sonnet   running   Add prompt storage

  (no work)
    p12 opus     running   Fix off-by-one
    p13 gpt-5.4  running

Run `meridian spawn show <id>` for details.
```

Grouped by work item. Columns: spawn id, model, status, description (last — optional, truncated if needed). No duration, cost, or operational details — use `spawn list` or `spawn show` for that. Hint at bottom nudges users to drill deeper.

### `meridian spawn show` (extended)

Default output adds work item and description fields. No `files_touched` by default — use `--files` flag for that.

```
Spawn: p5
Status: running
Model: claude-opus-4-6 (claude)
Duration: 238.8s
Space: s1
Work: auth-refactor
Desc: Implement step 2
Prompt: /path/to/.meridian/.spaces/s1/spawns/p5/prompt.md
Report: /path/to/.meridian/.spaces/s1/spawns/p5/report.md
```

### `meridian spawn` (extended)

- `--desc` flag (optional — description column shows last in `meridian work` output)
- `--work` flag (explicit work attachment, overrides session active work item)
- `prompt.md` written alongside params.json
- `work_id` snapshotted in spawn events

## Skills (baked into core)

- **`meridian-work`** — teaches operators when/how to create work items, write docs, sketch diagrams, use `$MERIDIAN_WORK_DIR`
- **`meridian-plan`** — teaches operators how to break work items into steps in `plan/` subdirectory

## Coordination Flow

1. Operator runs `meridian work`
2. Sees what work items are active and who's working on them
3. If overlap — reads the work item docs and runs `meridian spawn show <id>` to understand scope
4. Decides to wait or proceed based on context, not locks

Agents infer file boundaries from their work item docs and prompt. No advisory file claims — the docs and prompt ARE the coordination signal.

Small tasks: just spawn with `--desc`, no work item.
Big efforts: `meridian work start`, write docs, break into plan steps, coordinate spawns.

## Review Feedback (incorporated)

Five review spawns (p18–p22) evaluated the design. Key changes made:

- **`work_id` snapshotted on spawn** — not derived from ambient session state (consensus across all reviews)
- **`--desc` made optional** — reduce ceremony (UX review)
- **Added `state` enum to work.json** — `draft|ready|in_progress|blocked|done` alongside free-form `status` (UX review)
- **Dashboard-only `meridian work`** — use `spawn show` for detail (UX review)
- **Dropped `claimed_files`** — agents infer boundaries from work item docs + prompt context, `files_touched` handles diagnostics (coordination review discussion)
- **Text output is primary** — no `--format json` on coordination commands; JSON for JSONL stores and future viewer API (agentic review discussion)
- **`prompt.md` is forensics** — separate file, not the coordination surface (agentic review)
- **Env vars use `_DIR` suffix** — `MERIDIAN_SPACE_FS_DIR`, `MERIDIAN_WORK_DIR` (consistency fix)
- **Storage abstraction is file-authoritative** — don't over-promise backend swappability (architecture review)
- **Folded `design` into `work`** — one CLI command instead of two. `work/` directory, `work.json` metadata. No separate `meridian design` namespace.

## Resolved Questions

- **Non-meridian sessions**: If you didn't launch via `meridian start`, you don't have a session, so no work item tracking. `meridian spawn` still works (spawns get `work_id`), but primary session coordination requires meridian. If you use meridian, you get coordination. If you don't, you don't.
- **Cross-space visibility**: `meridian work` uses `$MERIDIAN_SPACE_ID` if in a space, shows all spaces if not. Follow existing space scoping convention.
- **`--desc` when omitted**: Description column shows last in `meridian work` output. No auto-derivation — either you gave one or you didn't.

## Open Questions

- `MERIDIAN_CHAT_ID` propagation bug — spawn p25 fixing this now. Not a blocker for work item propagation (`work_id` is snapshotted via `$MERIDIAN_WORK_DIR` directly, doesn't need session lookup), but should be fixed for general correctness.

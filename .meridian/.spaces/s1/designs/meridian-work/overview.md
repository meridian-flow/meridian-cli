# Meridian Coordination Layer — Design

## Problem

Operators (human or agent) have no way to see what's actively being worked on across a project. `meridian spawn list` shows spawn lifecycle (status, duration, cost) but not *intent* — what is this spawn doing, and what bigger effort is it part of?

## Design Decisions

- **Work items are a core concept.** Meridian is a coordination layer — work tracking is coordination. Opinionated, same level as spawns, reports, and skills.
- **Work items are git tracked.** Valuable working documents. Visible in PRs alongside code. Delete when done; git history preserves them.
- **No locks, no claimed_files.** Coordination through visibility, not mechanisms. Agents infer boundaries from work item docs and their prompt — same way a human developer reads the plan and knows what's someone else's area. `files_touched` (already tracked per spawn) serves as after-the-fact diagnostic.
- **Workspace-topology agnostic.** Shared-worktree and isolated-worktree workflows are both valid. Meridian records coordination state; skills and operator conventions decide how to collaborate.
- **Storage abstraction.** Local files today, file-backed and git-tracked. Interface should support a managed service later, but work items are file-authoritative — don't over-promise a clean backend swap.
- **`work/` is task-scoped, `fs/` is shared project context.** Each work item directory (`work/auth-refactor/`) contains design docs, plans, and diagrams for one major task — created via `meridian work start`, lives and dies with that effort. `fs/` is shared reference material across the project state root: architecture notes, team conventions, reference docs. A work item might reference stuff in `fs/`, but `fs/` doesn't belong to any particular work item.
- **Text output is the default.** Both humans and LLMs read text fine. Commands default to text unless the output is purely structured data meant for machine parsing (JSONL stores, piped output). `--format` is always available to override.
- **Env vars use `_DIR` suffix for paths.** `MERIDIAN_FS_DIR` and `MERIDIAN_WORK_DIR` are path env vars. `MERIDIAN_WORK_ID` carries the active work item id itself.
- **One command: `meridian work`.** Dashboard + management in one top-level command. No separate `design` namespace.

## Non-Goals

- Work items do not guarantee edit isolation, file ownership, or revert prevention.
- Meridian core does not prescribe shared-tree, worktree, branch, claim, or merge policy.
- Visibility is the core feature here. Enforcement, when desired, belongs to skills or external workflow tooling.

## Directory Layout

```
.meridian/
  work/              # git tracked — structured, meridian-managed
    auth-refactor/
      work.json
      overview.md
      auth-flow.mmd
      plan/
        step-1.md
        step-2.md
  fs/                # git tracked — freeform, agent-managed
  spawns/            # gitignored — ephemeral runtime state
    p5/
      params.json    # structured metadata (model, desc, work_id, etc.)
      prompt.md      # full prompt text — separate file, not in params.json
      output.jsonl   # harness output log
      stderr.log
      report.md
  spawns.jsonl       # gitignored
  sessions.jsonl     # gitignored
```

### .gitignore strategy

Ignore everything in `.meridian/` except `work/` and `fs/`:

```gitignore
# Ignore everything by default
*

# Track .gitignore itself
!.gitignore

# Track work/ and fs/ at the state root
!work/
!work/**
!fs/
!fs/**
```

## Work Items

Each work item is a directory with a `work.json` and freeform files:

```json
{
  "name": "auth-refactor",
  "description": "Extract session logic and add new middleware",
  "status": "implementing step 2",
  "created_at": "2026-03-08T..."
}
```

- `status` is the only lifecycle field and is free text — operators/LLMs set whatever makes sense
- `done` is the only distinguished status value — it marks the work item complete, hides it from active dashboard views, and makes it eligible for cleanup
- Can contain anything: markdown, mermaid diagrams, code snippets
- Plans live inside as `plan/` subdirectory when needed
- Work items are living documents — start rough, refine over time

### Work item ids and slug derivation

Work item names are slugified into ids:

- lowercase
- spaces and underscores become hyphens
- strip non-alphanumeric characters except hyphens
- collapse repeated hyphens
- max 64 characters
- on collision, append `-2`, `-3`, and so on

`work.json` stores the resolved slug in `name`, and commands accept either the original label at creation time or the slug afterward.

### Active Work Item (per session)

Active work item is persisted in the current session record in `sessions.jsonl` as `active_work_id`.

- `meridian work start` creates the work item if needed and sets `active_work_id` for the current session
- `meridian work switch <name>` changes the active work item for the current session
- `meridian work clear` unsets it for the current session
- concurrent terminals have independent sessions, so each terminal can have a different active work item
- spawns snapshot `work_id` at creation time, so later session changes do not retroactively move old spawns

Sets both `$MERIDIAN_WORK_DIR` and `$MERIDIAN_WORK_ID` for launched agents. Optional — spawns without a work item show up ungrouped.

### `work.json` concurrency

`work.json` uses last-writer-wins semantics. The file is small, updates are infrequent, and conflicts are self-correcting because the next status update overwrites stale text. No file locking is needed beyond atomic tmp+rename writes.

## Spawn Changes

### Prompt storage

Full prompt stored as a separate file per spawn — not embedded in `params.json` or JSONL:

```
spawns/p5/prompt.md     # full prompt text (forensics, debugging, viewer)
spawns/p5/params.json   # structured metadata (model, desc, work_id, etc.)
```

`prompt.md` is for forensics and deep inspection. For coordination, agents use `--desc` and work item context.

### Description and work attachment

Optional short label on spawn create:

```bash
meridian spawn -m opus --desc "Implement step 2" -p @prompt.md
```

`desc` and `work_id` are both snapshotted at spawn creation and stored in two places:

- `spawns/<id>/params.json` for per-spawn materialized metadata
- `spawns.jsonl` events for query-time reads and dashboard rendering

The dashboard reads `spawns.jsonl` as its single source of truth. It should not join across `params.json` files to recover description or work linkage.

`work_id` is snapshotted at creation time for both primary sessions and child spawns. Not derived from ambient session state at query time — the session/spawn owns its `work_id` permanently.

- **Primary session** (`meridian start`) — stores `active_work_id` in the session record
- **Child spawn** (`meridian spawn`) — captures resolved `work_id` and `desc` into `params.json` and spawn events

No registry of active sessions in `work.json` — derive it at query time from running sessions/spawns that have `active_work_id` or `work_id` set. Single source of truth, no drift.

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
meridian work                                  # dashboard — what's happening now
meridian work start "auth refactor"            # create work item + set as active
meridian work list                             # list all work items
meridian work list --active                    # hide items whose status is done
meridian work show auth-refactor               # show one work item + associated spawns
meridian work switch auth-refactor             # set active work item for current session
meridian work clear                            # unset active work item for current session
meridian work update auth-refactor --status "step 2"
meridian work done auth-refactor               # shorthand for --status done
```

Dashboard output:

```
ACTIVE
  auth-refactor          implementing step 2
    p5  opus     running   Implement step 2
    p6  gpt-5.4  running   Review step 1

  spawn-visibility       drafting design
    p9  sonnet   running   Add prompt storage

  (no work)
    p12 opus     running   Fix off-by-one
    p13 gpt-5.4  running

Run `meridian spawn show <id>` for details.
```

Grouped by work item. Columns: spawn id, model, status, description (last — optional, truncated if needed). No duration, cost, or operational details — use `spawn list` or `spawn show` for that. Hint at bottom nudges users to drill deeper.

`meridian work` and all its subcommands default to text output — both humans and LLMs read text. `--format json` is available when callers need structured data.

### `meridian work show`

Shows a single work item's metadata, file path, current status text, and associated spawns. This is the drill-down view before jumping into individual spawn details.

### `meridian spawn show` (extended)

Default output adds work item and description fields. No `files_touched` by default — use `--files` flag for that.

```
Spawn: p5
Status: running
Model: claude-opus-4-6 (claude)
Duration: 238.8s
Work: auth-refactor
Desc: Implement step 2
Prompt: /path/to/.meridian/spawns/p5/prompt.md
Report: /path/to/.meridian/spawns/p5/report.md
```

### `meridian spawn` (extended)

- `--desc` flag (optional — description column shows last in `meridian work` output)
- `--work` flag (explicit work attachment, overrides session active work item)
- `prompt.md` written alongside `params.json`
- `desc` and `work_id` snapshotted in spawn events

### Deletion

Work items are just directories. Delete them with `rm -rf .meridian/work/<id>` or `git rm -r .meridian/work/<id>`. No special `meridian work delete` command is needed.

## Boundary with `meridian-skills`

Meridian core owns coordination primitives:

- work items and their docs under `.meridian/work/`
- active work context for sessions and spawns
- spawn metadata such as `work_id` and `desc`
- operator-facing views like `meridian work` and `meridian spawn show`

`meridian-skills` owns coordination policy:

- how agents should read and update work docs
- when to stay in a shared worktree versus use an isolated branch or worktree
- merge, review, or handoff conventions
- any workflow-specific metadata beyond the core fields above

See [`../meridian-skills/overview.md`](../meridian-skills/overview.md) for the workflow-policy layer that sits on top of this design.

## Review Feedback (incorporated)

Five review spawns (p18–p22) evaluated the design. Key changes made:

- **`work_id` snapshotted on spawn** — not derived from ambient session state (consensus across all reviews)
- **`--desc` made optional** — reduce ceremony (UX review)
- **Dashboard-only `meridian work`** — use `spawn show` for detail (UX review)
- **Dropped `claimed_files`** — agents infer boundaries from work item docs + prompt context, `files_touched` handles diagnostics (coordination review discussion)
- **`prompt.md` is forensics** — separate file, not the coordination surface (agentic review)
- **Storage abstraction is file-authoritative** — don't over-promise backend swappability (architecture review)
- **Folded `design` into `work`** — one CLI command instead of two. `work/` directory, `work.json` metadata. No separate `meridian design` namespace.

### Post-review changes

After the initial review round, the design was updated again to match the current Meridian direction:

- removed all space-scoping assumptions; state lives directly under `.meridian/`
- replaced the dual `state` + `status` model with one free-text `status` field, with `done` as the only distinguished completion value
- text output is the default for all operator-facing commands (humans and LLMs both read text); `--format json` available when structured data is needed
- kept `MERIDIAN_FS_DIR` as-is and added `MERIDIAN_WORK_ID` alongside `MERIDIAN_WORK_DIR`
- defined slug derivation, session-scoped active work persistence, expanded lifecycle commands, and deletion-by-directory semantics
- made `spawns.jsonl` the dashboard's source of truth for both `desc` and `work_id`
- explicitly documented last-writer-wins semantics for `work.json`
- closed the old `MERIDIAN_CHAT_ID` concern after spawn p25 fixed the propagation issue
- moved collaboration workflow policy out of core and into the sibling `meridian-skills` design

## Resolved Questions

- **Non-meridian sessions**: If you didn't launch via `meridian start`, you don't have a session, so no active work item tracking. `meridian spawn` still works (spawns get `work_id`), but primary session coordination requires meridian. If you use meridian, you get coordination. If you don't, you don't.
- **`--desc` when omitted**: Description column shows last in `meridian work` output. No auto-derivation — either you gave one or you didn't.
- **`MERIDIAN_CHAT_ID` propagation**: Resolved by spawn p25. Work item propagation does not depend on it, but the general session/spawn context bug is no longer open.

## Open Questions

No design blockers currently. If future UX pressure appears around work item rename semantics, that can be handled as a follow-up without changing the storage model here.

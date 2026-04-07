# `__meridian-cli` Skill — Body Outline

## Purpose

One singular skill in meridian-base that teaches an agent **how to learn meridian** rather than re-documenting it. The agent walks away knowing:

1. The mental model — what meridian is, what it isn't, how state flows.
2. Where the CLI surfaces live and how to ask `--help` for any of them.
3. The principles `--help` cannot teach — JSON-output discipline, files-as-authority, idempotency, crash-only design, parent-session inheritance, config precedence.
4. The shape of the most common failure modes, with pointers (not procedures) for diagnosis.

It does **not** redocument flag tables, command lists, or examples that `--help` can produce on demand. Every reference section ends with a `meridian <thing> --help` or `mars <thing> --help` pointer instead.

## Frontmatter

```yaml
---
name: __meridian-cli
description: "Mental model and principles for the meridian and mars CLIs. Use when an agent needs to discover what meridian can do, learn a subcommand, diagnose a failure, or understand why meridian behaves the way it does. Points at `meridian --help` and `mars --help` as the canonical reference rather than duplicating them."
---
```

## Section Outline (target ≤ 180 lines)

### 1. What meridian is

Two paragraphs. Meridian is a thin coordination layer for multi-agent systems — not a runtime, not a database, not a workflow engine. It launches subagents through harness adapters (Claude, Codex, OpenCode), persists their state as JSONL events under `.meridian/`, and exposes that state through one CLI.

State on disk is the source of truth. If `cat spawns.jsonl | jq` doesn't show it, it doesn't exist. There is no daemon, no service, no in-memory cache that outlives the CLI process.

### 2. The CLI surface, by command group

A single small table with one row per top-level command group, each row pointing at `meridian <group> --help` or `mars <group> --help`. No flag enumeration. Roughly:

| Command group | What it covers | Where to learn more |
|---|---|---|
| `meridian spawn` | Create, wait, list, show, log, cancel, stats, reports for subagent runs | `meridian spawn --help` |
| `meridian work` | Work item lifecycle, dashboard, session listing | `meridian work --help` |
| `meridian session` | Read and search harness session transcripts | `meridian session --help` |
| `meridian models` | Model catalog and routing guidance | `meridian models list` |
| `meridian config` | Resolved config inspection and overrides | `meridian config --help` |
| `meridian doctor` | Health check, orphan reconciliation | `meridian doctor --help` |
| `meridian mars ...` | Bundled mars CLI for `.agents/` package management | `meridian mars --help` and `mars --help` |

### 3. Principles `--help` can't teach

Short subsections, each one paragraph, no command tables.

**Output mode discipline.** Agent mode defaults to JSON; human terminals get text. Parse `spawn_id` and `status` programmatically from JSON — never scrape prose from `--format text` output. The same command emits different shapes in the two modes; an agent that doesn't know to expect JSON will silently fail when run interactively or vice versa.

**Files as authority.** All state lives under `.meridian/` as JSONL events plus per-spawn artifact directories. There are no databases or services. If you can't see it on disk, it isn't there. Never edit `spawns.jsonl` or `sessions.jsonl` by hand — atomic writes assume an exclusive writer.

**Idempotent operations.** `meridian mars sync`, `meridian doctor`, and the read-side reconcilers all converge on correct state when re-run. If a spawn dies mid-execution, the next read-path command notices and marks it failed. Recovery is startup, not a separate code path.

**Config precedence.** CLI flag → `MERIDIAN_*` env var → agent profile YAML → project config → user config → harness default. **Each resolved field is evaluated independently** — a CLI `-m` override forces the harness to be derived from that model, not from the profile's harness. This catches a real class of bugs where an override "wins" partially.

**Parent session inheritance.** `$MERIDIAN_CHAT_ID` is inherited from the spawning session, so `meridian session log` and `meridian session search` read the parent's transcript by default — not the spawn's own (which is usually empty). This is the primary way a spawn recovers context from the conversation that launched it.

**Crash-only design.** No graceful shutdown. Atomic tmp+rename writes. Truncation-tolerant reads. The reaper runs on every read-path command. Designs that assume a "shutdown" hook will not survive contact with a SIGKILL.

### 4. Mars in one section

One paragraph: mars is the bundled package manager that materializes `.agents/` from sources declared in `mars.toml`. Meridian shells out to it via `meridian mars ...`. State files: `mars.toml` (committed, hand-edited), `mars.lock` (committed, generated), `mars.local.toml` (gitignored, local overrides). Drift detection lives in `meridian mars list --status` and `meridian mars doctor`. Never edit `.agents/` directly — it is regenerated by `meridian mars sync`.

End the section with a single pointer: `meridian mars --help` for the full command surface. No command table.

### 5. Diagnostics in one section

A short failure-mode table — only the patterns that aren't obvious from reading the spawn's own JSON output. This is the durable content from the old `__meridian-diagnostics` skill, slimmed.

| Symptom | Likely cause | First move |
|---|---|---|
| `orphan_run` / `orphan_stale_harness` in show output | Harness died without finalizing | Auto-recovered on next read; relaunch |
| `missing_wrapper_pid` / `missing_worker_pid` | Harness crashed on startup | `which claude` / `which codex`; reinstall if missing |
| Exit 127 / 2 with empty report | Harness binary not on `$PATH` | `which claude` / `which codex`; install if missing |
| Exit 143 / 137 | SIGTERM / SIGKILL — process killed externally | Check `dmesg` for OOM; otherwise treat as failed and retry |
| Timeout exit | Exceeded the configured runtime budget | Increase timeout in config or break the task into smaller spawns |
| Model error in `stderr.log` | API rejected the model | `meridian models list`; check API keys |
| Spawn directory missing | Crash during launch | Relaunch — state is recoverable |

The debugging sequence is one bullet list of pointers, not a procedure: `meridian spawn show` → `meridian spawn log` → `meridian session log` → `meridian doctor` → raw `spawns.jsonl` with `jq` as last resort. Each item is one line with the command name; no flag tables.

**Spawn artifact layout.** Every spawn writes to `.meridian/spawns/<id>/`. The contents are stable and worth knowing because `--help` doesn't teach the directory layout:

| File | Contents |
|---|---|
| `report.md` | Final report (if the spawn completed far enough to write one) |
| `output.jsonl` | Raw harness stdout — read via `meridian spawn log`, not directly |
| `stderr.log` | Harness stderr — errors, warnings, debug traces |
| `prompt.md` | The prompt sent to the harness |
| `harness.pid` | PID file for the harness process |
| `heartbeat` | Touched periodically while spawn is alive |

Status strings (`orphan_run`, `missing_wrapper_pid`, etc.) are defined in `src/meridian/lib/state/`. Implementation note: verify these literals against source before writing the SKILL body so the table doesn't drift silently.

### 6. Sessions in one section

Two short paragraphs — the durable content from the CLI half of `__meridian-session-context`:

`meridian session log <ref>` reads a session transcript. `<ref>` accepts a chat id (`c123`), spawn id (`p123`), or harness session id. Defaults to the latest compaction segment (`-c 0`); to recover full pre-compaction history, walk older segments by incrementing `-c 1`, `-c 2`, … until empty. `meridian session search <query> <ref>` runs a case-insensitive text search across all segments and emits navigation hints to jump to surrounding context.

`meridian work sessions <work_id>` lists every session that has touched a work item. Use `--all` to include archived sessions. Combined with parent-session inheritance, this is enough to walk an entire work item's conversation history.

End with: see `meridian session --help` and `meridian work sessions --help` for flag details.

### 7. Environment variables (one short table)

Only the variables an agent will actually need to read or set:

| Variable | Purpose |
|---|---|
| `MERIDIAN_STATE_ROOT` | Override `.meridian/` location |
| `MERIDIAN_DEPTH` | Spawn nesting depth (>0 = inside a spawn) |
| `MERIDIAN_FS_DIR` | Shared long-lived filesystem directory |
| `MERIDIAN_WORK_DIR` | Active work item scratch directory |
| `MERIDIAN_CHAT_ID` | Inherited parent session id (see "parent session inheritance" above) |

### 8. Where to go next

Three pointers:

- For delegation patterns and model selection, load `__meridian-spawn`.
- For work item lifecycle and artifact placement, load `__meridian-work-coordination`.
- For escalating tool permissions when a spawn hits capability limits, load `__meridian-privilege-escalation`.

## Style Constraints

- No role identity ("You are…").
- No imperative sequences ("First do X, then Y") unless the order is technically required.
- No model names hardcoded.
- No agent names from any layer (no `@reviewer`, no `@explorer`, no `@dev-orchestrator`). The skill is layer-zero.
- No prose that re-states what `--help` already says clearly. If a section feels like "the table from `--help` but in markdown", delete it and replace with a pointer.
- ≤ 180 lines including frontmatter and the section headings above. Reviewer estimate against this outline lands around 140 lines (with the spawn-artifact table and additional failure rows already factored in), so the budget has room. The point of consolidation is fewer lines, not the same lines in fewer files.

## Principle Duplication With `__meridian-spawn`

The current `__meridian-spawn` SKILL.md duplicates several of the principles in §3 (JSON output discipline at line 14, auto-recovery at line 97, `$MERIDIAN_FS_DIR` / `$MERIDIAN_WORK_DIR` definitions at lines 117–118). The consolidation resolves this duplication explicitly:

**Decision:** `__meridian-cli` is canonical for the principles. `__meridian-spawn` trims its restatements and relies on co-loading.

This is safe because, after the consumer-profile updates in `06`, every profile that loads `__meridian-spawn` either also loads `__meridian-cli` or is the orchestrator base profile (which loads CLI skills ad-hoc). The implementer must verify that no profile loads `__meridian-spawn` without also loading `__meridian-cli` *before* deleting any duplicated lines from `__meridian-spawn`. If a profile is found that breaks the assumption, add `__meridian-cli` to it as part of the same phase.

Specific edits to `__meridian-spawn/SKILL.md` once `__meridian-cli` is in place:

- Trim line 14 ("All CLI output is JSON…") to a one-line cross-reference.
- Trim line 97 ("Stuck spawns auto-recover…") to a one-line cross-reference.
- Remove the env-var definitions on lines 117–118; let `__meridian-cli` own them.
- **Bug fix while the file is open:** line 57 says `meridian mars models -h`. That command does not exist. The correct command is `meridian models -h`. Fix unconditionally — this is a pre-existing bug surfaced during review, and the cheap moment to fix it is in the same PR.

## What Goes in `resources/` (if anything)

Nothing in v1. The whole skill is meant to be small. If a future addition needs depth (e.g. a long-form architecture overview), it goes under `resources/` and the SKILL body links to it — but resources are not part of the consolidation deliverable.

The one open question is the `mars-toml-reference.md` schema file from the deleted `__mars/` skill — see Gap 8 in `04-cli-help-gaps.md`. If the planner picks resolution option 2 there (preserve the resource under `__meridian-cli/resources/`), this paragraph is the place to allow it as an exception, with a one-sentence justification.

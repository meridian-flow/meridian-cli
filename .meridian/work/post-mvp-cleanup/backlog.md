# post-mvp-cleanup — Backlog

> This is a **backlog work item**, not a scoped delivery. It captures
> engineering concerns that were deliberately deferred during MVP
> shaping so the MVP could stay cheap and focused. Nothing in here
> should be touched until the MVP validates with its first customer —
> at which point we triage these, promote some into real work items,
> and archive the rest.

## Context

During the agent-shell-mvp reframe (April 2026), several concerns came
up that are legitimately valuable but would bloat the MVP scope. The
MVP rule was: **pull in only what a single customer needs to see a
working `meridian app` demo of Claude Code with bidirectional steering.
Everything else waits.**

This file is where "everything else" lives.

## Items

### 1. Rewrite meridian CLI in Go

**Status.** Committed direction, not a hypothetical. Happens
regardless of whether the `meridian app` UI work validates —
the language choice is independent of the UI product question.

**Motivation (two independent drivers, either would be sufficient).**

1. **Concurrency fit.** Meridian's job is orchestrating many
   simultaneous connections: multiple spawns running in parallel,
   each with stdin/stdout/control channels, plus file watchers,
   reapers, and (eventually) WebSocket fanout to a UI. This is
   exactly what Go was designed for — goroutines per connection,
   channels for coordination, cheap cancellation. Python's asyncio
   works, but it's working *against* the runtime instead of with it:
   subprocess management with asyncio is a known sharp-edge area
   (PTY handling, stdin buffering, signal propagation, zombie reaping).
   The original Python choice was made before it was clear how much
   concurrent orchestration the system would actually do. **In
   retrospect, Go was the right call from day one.**

2. **Distribution.** Python ships as a runtime-plus-venv story
   (pipx, uv, version conflicts, dependency resolution). Go ships
   as a single static binary. "Download one file, run it" is a real
   product advantage for non-technical users and for demo moments,
   and matters even more if `meridian app` ever becomes a desktop
   install target.

**Why deferred (briefly).** The Go rewrite is 2–4 weeks of focused
work that freezes all other feature development on meridian-channel
while it happens. The MVP has to ship first so there's something real
to validate; the rewrite comes after that. This is sequencing, not
reconsideration — the destination is committed.

**What we already have (ground truth from April 2026 exploration).**

- `meridian-llm-go` exists in multiple parallel repos
  (`meridian/`, `meridian-agents/`, `meridian-collab/`, `meridian-flow/`).
  **It is an LLM HTTP API client library** — provider registry,
  Anthropic/OpenRouter streaming, tool registry, schemas. It is
  **NOT a Claude Code subprocess wrapper**. Do not assume it gives
  you a head start on wrapping the `claude` CLI — it gives you
  streaming primitives and Go project infrastructure, which is
  different and smaller leverage than it sounds.
- `meridian-stream-go` also exists in the same four repos. Worth
  inspecting in detail when this work is picked up — it may contain
  stream-json handling that would actually be reusable for Claude
  Code harness wrapping.

**Open scoping questions for when this is picked up.**

- **Full CLI rewrite vs `meridian app` binary only?** Does the Go
  migration mean rewriting all of `meridian` (including `work`,
  `spawn`, `session`, `mars`, `config`, `doctor`), or just the
  user-facing app binary while leaving the Python dev CLI alone?
- **State layer.** `.meridian/` JSONL event stores, atomic writes,
  file locks — all implemented in Python today. Reimplementing in
  Go has to preserve backward compatibility with on-disk state so
  existing `.meridian/` directories keep working.
- **Harness adapter migration order.** Claude first (primary use
  case), then Codex, then OpenCode? Or all at once?
- **Mars integration.** Mars is already Rust. How does a Go meridian
  CLI shell out to it vs depend on it differently?
- **Agent profiles.** YAML parsing, skill loading, permission
  resolution — all Python today. Port or reshape?
- Is a new Go package (e.g. `meridian-harness-go`) the right home
  for subprocess-wrapping code, separate from `meridian-llm-go`?
- How does this interact with D40 (see item 3 below)?

**What we already have (ground truth from April 2026 exploration).**

- `meridian-llm-go` exists in multiple parallel repos
  (`meridian/`, `meridian-agents/`, `meridian-collab/`, `meridian-flow/`).
  **It is an LLM HTTP API client library** — provider registry,
  Anthropic/OpenRouter streaming, tool registry, schemas. It is
  **NOT a Claude Code subprocess wrapper**. Do not assume it gives
  you a head start on wrapping the `claude` CLI — it gives you
  streaming primitives and Go project infrastructure, which is
  different and smaller leverage than it sounds.
- `meridian-stream-go` also exists in the same four repos. Worth
  inspecting in detail when this work is picked up — it may
  contain stream-json handling that would actually be reusable for
  Claude Code harness wrapping.

**Open scoping questions for when this is picked up.**

- Does the "Go CLI" mean rewriting the whole `meridian` CLI, or just
  the `meridian app` binary (single user-facing binary) while leaving
  the Python dev CLI alone for internal dev workflows?
- Is a new Go package (e.g. `meridian-harness-go`) the right home for
  subprocess-wrapping code, separate from `meridian-llm-go`?
- How does this interact with D40 (see item 3 below)?

### 2. Consolidate scattered code across the four parallel repos

**Observation.** Four repos share nearly identical structure:

| Repo | Last touched | Notes |
|---|---|---|
| `meridian/` | Mar 31 | oldest |
| `meridian-agents/` | Feb 13 | stale |
| `meridian-flow/` | Apr 8 | recent, biomedical framing |
| `meridian-collab/` | Apr 5 | recent, has `frontend-v2` + latest git activity |

Each has its own `backend/`, `cli/`, `frontend/`, `meridian-llm-go/`,
`meridian-stream-go/`. This is parallel iteration — the same code
reimagined four times under different framings.

**Why deferred.** Consolidation for its own sake slows the MVP down.
The MVP only needs one home (meridian-channel) and enough code
pulled in to demo. The other repos can sit until the MVP validates
and we know which consolidation direction pays off.

**Decisions needed when picked up.**

- Which repo is the canonical source for each concern (CLI, backend,
  frontend, Go libs)?
- Are any of `meridian/`, `meridian-agents/`, `meridian-collab/`,
  `meridian-flow/` safe to archive outright?
- Does `frontend-v2` (currently duplicated in `meridian-collab/` and
  `meridian-flow/`) have a single canonical home yet?

### 3. Re-evaluate D40 under post-MVP architecture

**What D40 said.** `providers/claude-code/` is explicitly NOT going
into `meridian-llm-go`. The rationale was that meridian-flow was the
consumer and the shell path didn't go through `meridian-llm-go`.

**Why revisit.** The framing has changed. Post-MVP, if we rewrite the
CLI in Go, the question becomes: where does Claude Code CLI wrapping
live in the Go ecosystem? Options:

- **In `meridian-llm-go`** — rejected by D40. May still be wrong
  because CLI wrapping is architecturally different from HTTP API
  streaming.
- **A new package** (e.g. `meridian-harness-go`) dedicated to
  subprocess-harness wrapping, sibling to `meridian-llm-go`.
- **Direct in the `meridian app` binary** without a reusable library
  layer, at least initially.

**Decision to make.** Which of those three shapes we adopt. Worth
making before the Go rewrite starts, not during.

### 4. Decide what happens to the original `agent-shell-mvp` design tree

**Context.** Before the MVP reframe, `agent-shell-mvp/design/` was
built around meridian-flow as a Go backend consumer. That framing no
longer holds. The design tree has specific artifacts that are still
valuable and should not be lost:

- `findings-harness-protocols.md` — tier-1 determination for all
  three harnesses, mid-turn steering semantics. **Keep.**
- `refactor-touchpoints.md` — 37-file impact map of meridian-channel's
  harness layer. **Keep.**
- The rest of `design/` — invalidated by the reframe, can be archived
  or deleted.

**Why deferred.** Cleaning up the design tree is not MVP-blocking. It
becomes cleanup once the MVP is clearly the active direction.

### 5. Re-examine what the MVP actually pulled in vs what got left behind

Once the MVP ships and validates, do a retrospective of what got
pulled into meridian-channel during the MVP build and what stayed
scattered. Some of what stayed scattered will turn out to be worth
consolidating; some of what got pulled in may turn out to be
redundant with existing code. Don't do this mid-MVP — it's a
post-validation hygiene pass.

## Triage Policy

When this work item is picked up:

1. Read this file from the top.
2. For each item, decide: **promote to its own work item**, **defer
   further**, or **archive**.
3. Don't try to do all of them at once. Pick the one with the highest
   leverage for the next milestone and ignore the rest.
4. Delete items from this file as they get promoted or archived —
   this file should shrink, not grow.

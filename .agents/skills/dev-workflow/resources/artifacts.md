# Tracking Artifacts

Reference this when writing entries to `decision-log.md`, `implementation-log.md`, or creating the initial `overview.md`. These formats keep tracking consistent across work items and sessions.

Artifact placement policy comes from `__meridian-work-coordination`. This file only defines the content and format of work-scoped artifacts that already live under `$MERIDIAN_WORK_DIR`.

## overview.md Template

Create this during the design phase. It's the primary design document — the thing another engineer reads to understand what you're building and why.

```markdown
# {Work Item Title}

## Problem

What's wrong, what's missing, or what opportunity exists.
Be specific about the pain point. "The auth system is slow" is weak.
"Token validation makes a database round-trip on every request, adding 50ms
to all authenticated endpoints" is useful.

## Approach

How you're solving it. Include enough detail that a coder agent can
implement from this without guessing at your intent.

Cover:
- Key architectural decisions (and why you chose them)
- What's in scope and what's explicitly out of scope
- Integration points with existing code
- Migration strategy (if changing existing behavior)

## Architecture

How the pieces fit together. This can be prose, a diagram, or both.
Focus on the boundaries — what talks to what, what owns what state.

If the architecture is simple enough to explain in a paragraph, skip the
diagram. If it's complex enough to need a diagram, make one.

## Open Questions

Anything unresolved that might affect implementation. Remove items as they
get decided (move them to decision-log.md).

- [ ] Question 1
- [ ] Question 2
```

Adapt this template freely. Some work items need a detailed architecture section; others need two sentences. The template shows what's available, not what's required.

## decision-log.md Entry Format

Decisions are append-only and immutable. Once recorded, they don't get edited or deleted — if a decision is reversed, record a new decision that supersedes it.

This matters because subagents and future sessions need to understand not just what was decided, but why, and what alternatives were considered. Without this, agents re-derive decisions or silently contradict earlier choices.

### Entry format

```markdown
## D-{N}: {Decision Title}

**Date:** {YYYY-MM-DD}
**Status:** accepted | superseded by D-{M}

**Decision:** {What was decided, stated clearly.}

**Rationale:** {Why this choice over the alternatives. Include the reasoning
that would convince a skeptical reviewer.}

**Alternatives Considered:**
- {Alternative A} — rejected because {reason}
- {Alternative B} — rejected because {reason}
```

### Examples

```markdown
## D-1: Use middleware pattern for auth

**Date:** 2026-03-10
**Status:** accepted

**Decision:** Implement token validation as middleware that runs before route
handlers, rather than as a decorator on individual handlers.

**Rationale:** Middleware ensures auth can't be accidentally omitted from new
endpoints. The decorator pattern requires every handler author to remember to
apply it, which is error-prone. The middleware approach also centralizes the
token validation logic for easier auditing.

**Alternatives Considered:**
- Per-handler decorators — rejected because they rely on developer discipline
  and are easy to forget on new endpoints
- Auth at the reverse proxy layer — rejected because we need user context in
  the application layer for authorization decisions
```

```markdown
## D-4: Defer rate limiting to Phase 2

**Date:** 2026-03-10
**Status:** accepted

**Decision:** Ship auth middleware without rate limiting in the initial
implementation. Add rate limiting as a follow-up.

**Rationale:** Rate limiting adds complexity (storage backend, configuration,
per-endpoint tuning) that would delay the core auth work. The auth middleware
is useful without it, and adding it later is additive — it won't require
reworking the middleware.

**Alternatives Considered:**
- Include rate limiting now — rejected because it doubles the scope and the
  core auth work is independently valuable
```

### Numbering

Entries are numbered sequentially: D-1, D-2, D-3, etc. Never reuse a number. If D-3 gets superseded, it stays as D-3 with `Status: superseded by D-7` — and D-7 explains the new decision.

## implementation-log.md Entry Format

The implementation log captures findings during implementation — things that aren't decisions but need to be recorded so they don't get lost. Bugs found, unexpected behaviors, backlog items discovered, deferred review findings, and coordination notes.

Unlike the decision log, entries here are informational. They describe what was found, not what was decided. If a finding leads to a decision, record the decision separately in `decision-log.md`.

### Entry format

```markdown
## IL-{N}: {Title}

**Date:** {YYYY-MM-DD}
**Category:** {bug | unexpected | backlog | deferred | coordination}
**Phase:** {Phase number or "design" / "review"}

**Description:** {What was found.}

**Evidence:** {File paths, error messages, reproduction steps — whatever
makes this concrete rather than vague.}

**Suggested Action:** {What should be done about it, or "needs investigation."}
```

### Category tags

| Category | When to use | Example |
|----------|-------------|---------|
| `bug` | Something is broken, but fixing it now would derail the current phase | "Token refresh silently swallows network errors" |
| `unexpected` | Surprising behavior that implementers should know about | "The ORM generates N+1 queries for this join" |
| `backlog` | Work needed but out of current scope | "Error messages need i18n support" |
| `deferred` | Explicitly deferred from current work — often from review findings | "Reviewer flagged missing input validation on admin endpoints" |
| `coordination` | Overlap with another work item or external dependency | "This touches the same auth module as work item X" |

### Examples

```markdown
## IL-1: Token model uses string comparison for expiry

**Date:** 2026-03-10
**Category:** bug
**Phase:** 2

**Description:** The existing `Token.is_expired()` method compares timestamps
as strings rather than datetime objects. This works by accident in most cases
but breaks around midnight UTC on month boundaries (e.g., "2026-03-9" > "2026-03-10"
as strings).

**Evidence:** `src/auth/models.py:47` — `return self.expires_at > datetime.now().isoformat()`

**Suggested Action:** Fix in Phase 3 when we're already modifying the token model.
Low risk until month boundaries.
```

```markdown
## IL-5: Overlap with ws-transport-v2 on connection auth

**Date:** 2026-03-11
**Category:** coordination
**Phase:** 3

**Description:** The ws-transport-v2 work item is also modifying connection
authentication. Their design doc uses a different token format for WebSocket
connections. We need to ensure both approaches can coexist.

**Evidence:** See `meridian work show ws-transport-v2`, specifically
`overview.md` section on connection authentication.

**Suggested Action:** Read their design doc before implementing Phase 3.
Design the middleware to accept both token formats, or coordinate with
that work item's orchestrator.
```

### Numbering

Sequential: IL-1, IL-2, IL-3, etc. Never reuse numbers. The log is append-only.

## General Principles

- **Append-only.** Both logs only grow. Don't edit or delete entries. If something changes, add a new entry that references the old one.
- **Concrete over vague.** "There might be a performance issue" is useless. "The query at `src/db.py:123` does a full table scan on a 10M row table" is useful.
- **Date everything.** Entries without dates become impossible to sequence when reading the log later.
- **Cross-reference.** When a finding leads to a decision, reference it: "See D-4" or "Logged as IL-7." When a decision supersedes another, say so explicitly.

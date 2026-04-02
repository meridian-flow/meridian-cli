---
name: issues
description: Mirror local tracking artifacts to GitHub Issues for team visibility. Use this whenever you find bugs, unexpected behavior, deferred decisions, or backlog items during implementation, investigation, or review — anything worth tracking beyond the current work item. Also use when asked to file an issue or when you've investigated a problem and determined it needs a GH issue rather than a quick fix.
---

# Issue Tracking

This skill assumes `/__meridian-work-coordination` already defines work ownership and artifact placement. Spawn reports and work-scoped notes are the source of truth. GitHub Issues are a visibility layer — they give the team searchability, linkability, and a shared view of what was found during agent work.

If `gh` is unavailable, everything works fine with local tracking only. No errors, no warnings. Issues are a bonus, not a requirement.

## Availability Check

Before creating any issue, verify that `gh` is usable:

```bash
gh auth status 2>/dev/null && gh repo view --json name 2>/dev/null
```

If either command fails — `gh` isn't installed, authentication is missing, or the repo isn't on GitHub — skip issue creation silently. Log the finding locally and move on. The agent's job is implementation, not fighting with tooling.

## When to Create a GitHub Issue

Create an issue when you find something worth tracking that you can't or shouldn't address right now. The common situations:

**Bug found during implementation** — You hit a bug in adjacent code, but fixing it would pull you off your current phase. Log it locally *and* file an issue so it doesn't get lost.

**Unexpected behavior** — Something works but behaves surprisingly. Not broken enough to stop, but someone should investigate. These often become the bugs of next week.

**Backlog item discovered** — You notice something that needs doing (cleanup, missing test, hardcoded value) but it's out of scope for the current work item.

**Deferred design decision** — A decision came up that needs more context or broader input before it can be made. You picked a reasonable default and moved on, but the real decision is still open.

**Review finding (deferred)** — A reviewer flagged something HIGH or MEDIUM severity but agreed it's not blocking the current work. File it so it gets addressed in a future pass.

### Quick Decision Rule

- **Fix immediately** if it takes < 5 minutes and you're already in the area
- **File an issue** if it would derail your current task, requires broader context, or needs design discussion

## When NOT to Create a GitHub Issue

**Critical review findings** — Fix these immediately. They don't belong in a backlog.

**Things you're fixing in this phase** — If it's part of your current work, just fix it. Don't create tracking overhead for work in progress.

**Decisions already made** — If a decision is already made and implemented, there's nothing to track. The decision is done.

## Labels and Issue Format

Use labels consistently so the team can filter by category — tag every issue with what it is and which work item found it (`work:<slug>`). Every issue body should answer three questions: where was this found, what is it, and what should be done about it.

See [`resources/gh-commands.md`](resources/gh-commands.md) for the full label taxonomy with colors, the issue body template, and all `gh` CLI commands.

## Quick Example

You're implementing step 3 of `auth-refactor` and discover that the token refresh logic silently swallows errors:

1. Note it in your spawn report or work directory — this is the source of truth
2. Check `gh` availability
3. If available, create the issue:

```bash
gh issue create \
  --title "Bug: token refresh silently swallows errors" \
  --label "bug,work:auth-refactor" \
  --body "$(cat <<'EOF'
## Context
Found during: auth-refactor, step 3 (token validation)
Found by: implementer (p107)

## Description
Token refresh in `src/auth/refresh.py:45` catches all exceptions and returns
`None` instead of propagating. This masks network errors, expired credentials,
and malformed responses identically.

## Evidence
- `src/auth/refresh.py:45-52` — bare `except: return None`
- Discovered when a test passed despite invalid credentials

## Suggested Action
Replace bare except with specific exception handling. At minimum, log the
error before returning None. Ideally, distinguish retryable (network) from
permanent (invalid credentials) failures.

---
*Created by meridian agent during `work:auth-refactor` implementation*
EOF
)"
```

## Proactive Mining

Focused implementers and reviewers produce better primary work when they are not splitting attention to hunt backlog items. A dedicated mining pass at natural breakpoints keeps both outcomes higher quality: the main phase stays focused, and backlog capture gets a fresh, deliberate pass.

If you have access to conversation history, use it to mine deferred items that are easy to lose: "come back to this" notes, TODOs discussed but not executed, and alternatives rejected for now but worth revisiting later.

Then scan touched files and nearby code for debt markers such as `TODO`, `FIXME`, `HACK`, dead code, hardcoded values, and missing error handling. For each finding, either create a new GH issue or comment on an existing related issue. Triage aggressively: skip trivial noise, avoid duplicates, and only track items that are meaningful beyond the current phase.

## Workflow Integration

Issue tracking fits naturally into the implementation and review cycles:

- **During implementation**: When you encounter something outside your current scope, log it locally first, then mirror to GitHub if available.
- **During review**: Deferred findings (HIGH/MEDIUM that aren't blocking) get both a local log entry and an issue.
- **At phase boundaries**: Quick scan of issues tagged with your `work:<slug>` gives a summary of everything discovered during that phase.
- **On completion**: Issues created during a work item serve as the handoff backlog for follow-up work.

## Reference

For `gh` CLI command details, the full label taxonomy with hex colors, the issue body template, and label creation commands, see [`resources/gh-commands.md`](resources/gh-commands.md).

---
name: dev-workflow
description: Development lifecycle orchestration — sequencing design, review, planning, and implementation phases with multi-agent coordination. Use this whenever you're working on a feature, refactor, or bug fix that involves more than one step. Activate for any task that benefits from phased execution, subagent delegation, or structured review — even if the user doesn't explicitly ask for a "workflow."
---

# Dev Workflow

You are a development lifecycle orchestrator. You sequence work through phases, delegate coding and reviewing to subagents, and keep state visible so that any agent — including yourself in a future session — can pick up where things left off.

This skill is the conductor, not the instrumentalist. It knows the sequence of phases and when to invoke what, but the phase-specific skills (`design`, `plan-implementation`) teach the actual craft for those phases. Read them when you enter their territory.

This skill assumes `__meridian-work-coordination` already owns work setup, status semantics, and artifact placement. Use `$MERIDIAN_WORK_DIR` for work-scoped tracking, and do not redefine `.meridian/fs/` usage here.

## The Lifecycle

Work moves through five phases. Set the current phase with `meridian work update --status <status>` so state is always visible.

```
designing → reviewing → planning → implementing → done
```

Not every task needs every phase. Scale the ceremony to the complexity — see "Routing by Complexity" below.

### Status vocabulary

| Status | Meaning |
|--------|---------|
| `designing` | Exploring the problem space, writing design artifacts |
| `reviewing` | Design is written, reviewers are stress-testing it |
| `planning` | Design is approved, decomposing into implementation phases |
| `implementing` | Plan exists, executing phase by phase |
| `done` | All phases complete, tests pass, work is shippable |

## Routing by Complexity

Before starting, assess the task. Over-coordinating simple work creates more noise than value — more agents means more chances for miscommunication on tasks that one agent could handle alone.

**Trivial** — typo, config change, one-liner fix
Do it yourself or spawn a single coder. No reviewers, no verifier. Commit and move on.

**Small** — scoped bug fix, simple feature addition, fewer than 5 files
Skip design and review. Go straight to `implementing`. Coder → verifier → one reviewer (pick the most relevant lens). Single phase, no plan files needed.

**Medium** — multi-file feature, moderate refactor, new module
Lightweight design (just `overview.md`), skip adversarial design review. Plan with 2-4 phases. Coder → verifier → two reviewers per phase.

**Complex** — architecture change, new subsystem, cross-cutting refactor
Full lifecycle. Design doc, adversarial design review, detailed planning, multiple phases with full review gauntlet. This is what the workflow was built for.

**Exploratory** — unclear scope, needs investigation before committing
Spawn a `researcher` to understand the landscape first, then decide which tier the actual work falls into.

The common thread: make state visible (statuses), make decisions durable (logs), and verify before proceeding (reviews + tests — scaled to the tier).

## Phase Transitions

### Entering design (`designing`)

```bash
meridian work start "descriptive name"
meridian work update $MERIDIAN_WORK_ID --status designing
```

Read the `design` skill — it has the methodology for researching the codebase, writing `overview.md` and `decision-log.md`, and collaborating with the user on approach.

Before designing, check for overlapping work: run `meridian work list`. If another work item touches the same area, read its design doc and design around it. Note the overlap in `implementation-log.md` with category `coordination`.

### Entering review (`reviewing`)

```bash
meridian work update $MERIDIAN_WORK_ID --status reviewing
```

Fan out 2-3 reviewers in parallel, each with a different lens:

```bash
meridian spawn -a reviewer-solid -p "Review this design for correctness and maintainability" \
  -f $MERIDIAN_WORK_DIR/overview.md -f $MERIDIAN_WORK_DIR/decision-log.md

meridian spawn -a reviewer-planning -p "Review this design for architectural fit" \
  -f $MERIDIAN_WORK_DIR/overview.md -f [relevant codebase files]
```

Synthesize findings by severity:
- **CRITICAL** — fundamental flaw, must address before proceeding
- **HIGH** — significant concern, decide whether to fix or accept with rationale
- **MEDIUM/LOW** — note in decision-log or implementation-log, move on

When reviewers disagree, you make the call. Record the decision in `decision-log.md`. If you're genuinely unsure, escalate to the user. If the design changed substantially after review, consider one more round — but don't loop more than twice.

Design review is done when all CRITICAL findings are resolved and HIGH findings are either fixed or explicitly accepted with recorded rationale.

### Entering planning (`planning`)

```bash
meridian work update $MERIDIAN_WORK_ID --status planning
```

Read the `plan-implementation` skill — it has the methodology for decomposing designs into phases, writing phase files, mapping dependencies, and estimating agent headcount.

### Entering implementation (`implementing`)

```bash
meridian work update $MERIDIAN_WORK_ID --status implementing
```

Start `implementation-log.md` at the beginning of this phase. Append entries as you go — bugs found, unexpected behaviors, backlog items discovered, deferred review findings. Read `resources/artifacts.md` for entry formats.

### Marking done

```bash
meridian work update $MERIDIAN_WORK_ID --status done
# or: meridian work done $MERIDIAN_WORK_ID
```

Before marking done:
- All phases are implemented and reviewed
- Tests pass across the full suite (not just phase-level checks)
- `implementation-log.md` has no unresolved CRITICAL items
- Deferred items are tracked (in `implementation-log.md`, or as GH issues via an investigator)

## The Implementation Loop

This is the core rhythm during `implementing`. Repeat for each phase in the plan.

### Step 1: Spawn the coder

Give the coder everything it needs — design docs, phase scope, relevant existing code. Be specific about boundaries.

```bash
meridian spawn -a coder -m codex \
  -p "Phase N: [clear description of what to implement]" \
  -f $MERIDIAN_WORK_DIR/overview.md \
  -f $MERIDIAN_WORK_DIR/plan/phase-N-slug.md \
  -f [relevant source files]
```

### Step 2: Evaluate the report

Read the coder's report. Did it follow the design? Any deviations or surprises?

If the coder flagged tangential issues — bugs in adjacent code, surprising behavior — don't investigate them yourself. Spawn an investigator (see "The Investigator Pattern" below). Don't block the review step on it.

### Step 3: Verify

Spawn a verifier to run the project's test suite, type checker, and linter. The verifier fixes mechanical failures (import errors, type annotations, formatting) and reports real issues back. This cleans up the implementation before reviewers see it — reviewers shouldn't waste time on things a type checker catches.

```bash
meridian spawn -a verifier -p "Verify Phase N: run tests, type check, lint. Fix what's mechanical, report what's real." \
  -f [changed files]
```

### Step 4: Fan out reviewers

Launch 2-3 reviewers in parallel with different lenses:

```bash
meridian spawn -a reviewer-solid -p "Review Phase N implementation" -f [changed files]
meridian spawn -a reviewer-concurrency -p "Review Phase N implementation" -f [changed files]
meridian spawn wait $SPAWN_ID_1 $SPAWN_ID_2
```

### Step 5: Synthesize and fix

Apply the severity framework:

| Severity | Action |
|----------|--------|
| CRITICAL | Fix now. Spawn a targeted fix, then re-review. |
| HIGH | Decide: fix now or defer. Record the decision. |
| MEDIUM | Spawn an investigator to assess — quick-fix or file a GH issue. |
| LOW | Log if noteworthy. Otherwise move on. |

### Step 6: Fix-and-re-review cycle

If there are issues to fix:

```bash
meridian spawn -a coder -m codex \
  -p "Fix these review findings in Phase N: [specific findings]" \
  -f [review reports] -f [affected files]
```

Then re-review the fixes. Cap this at 3 cycles — if you haven't converged by then, something is structurally wrong. Escalate to the user.

### Step 7: Phase gate

Before moving to the next phase:
- Tests pass
- Changes are committed with a descriptive message
- Plan status is updated
- Any deferred items are logged in `implementation-log.md`

If a phase reveals that the plan needs adjustment, update the phase files and record the change in `decision-log.md`.

## The Investigator Pattern

During implementation, coders and reviewers will flag things that aren't part of the current task — bugs in adjacent code, surprising behavior, potential improvements. These are real findings, but chasing them mid-phase creates drift.

Instead, spawn an `investigator`:

```bash
meridian spawn -a investigator -p "Investigate: [what was flagged]" -f [relevant files]
```

The investigator briefly researches the issue and either quick-fixes it (if trivial and safe) or files a GH issue with its findings. This happens in the background — the main implementation loop continues without blocking.

You don't need the `issue-tracking` skill yourself. The investigator carries it. Your job is to decide *what* gets investigated, not to file issues directly.

## Cross-Workspace Coordination

When multiple work items are in flight:

1. **Before designing**, run `meridian work list` and read overlapping work items' design docs. Design around them, not through them.
2. **During implementation**, if parallel work in another workspace touches overlapping files, note it in `implementation-log.md` (category: `coordination`) and prefer separate worktrees so file changes don't conflict.
3. **Worktrees** keep parallel work isolated:

```bash
git worktree add ../project-feature-name feature-branch
```

Each worktree's orchestrator sees its own files but can read other work items' docs via `meridian work list` and `meridian work show`.

## Tracking Artifacts

All tracking lives in `$MERIDIAN_WORK_DIR/` as markdown files:

```
$MERIDIAN_WORK_DIR/
  overview.md              # Design: problem, approach, architecture
  decision-log.md          # Append-only decisions (D-1, D-2, ...)
  implementation-log.md    # Append-only findings (IL-1, IL-2, ...)
  plan/
    phase-1-slug.md        # Per-phase implementation specs
    phase-2-slug.md
    ...
```

Read `resources/artifacts.md` for entry formats when writing to `decision-log.md` or `implementation-log.md`.

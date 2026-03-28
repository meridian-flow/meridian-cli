---
name: dev-orchestration
description: Development lifecycle orchestration — sequencing design, review, planning, and implementation phases with multi-agent coordination. Use this whenever you're working on a feature, refactor, or bug fix that involves more than one step. Activate for any task that benefits from phased execution, subagent delegation, or structured review — even if the user doesn't explicitly ask for a "workflow."
---
# Dev Orchestration

You orchestrate work phases, delegate execution and review, and keep state visible so future agents can resume cleanly.

This skill defines phase sequencing and judgment. Use `architecture-design` and `plan-implementation` for phase-specific craft. `__meridian-work-coordination` owns work setup, status semantics, and artifact placement.

## Phases of Work

Work moves through phases — research, design, planning, implementation, testing, documentation, or whatever the task requires. Not every task needs all of these; many skip straight to implementation. The orchestrator's job is to recognize which phases matter for the current work and sequence them appropriately.

Track current focus with `meridian work update --status <status>`. Status is free-form — use whatever label fits: `researching`, `designing`, `planning`, `implementing`, `testing`, `done`, etc.

Review is woven through every phase, not a separate step. What review looks like depends on the phase — stress-testing an approach during design, sanity-checking boundaries during planning, verifying correctness during implementation.

Scale to the work. A bug fix might be one phase. A system redesign might be five.

## Scaling Ceremony

The biggest mistake is over-coordinating simple work or under-coordinating complex work. Two questions help calibrate:

1. **How much surface area?** More files and modules touched → more value from design and planning upfront.
2. **How reversible are mistakes?** Schema changes, API contracts, and public interfaces are expensive to get wrong — worth a design review. Internal refactors are cheap to fix — lighter process.

Skip straight to implementation when the intent is obvious and the blast radius is small. Add design when there are genuine tradeoffs. Add more phases when work crosses module boundaries, changes interfaces, or requires coordination with other efforts.

## Design

Read `architecture-design` for method. Before designing, check `meridian work list` — if another work item touches the same area, read its design doc so efforts don't conflict. Surface significant overlap to the user.

When the design feels solid, fan out reviewers to stress-test it. Read `review-orchestration` for how to choose focus areas, select models, and synthesize findings.

## Planning

Read `plan-implementation` for phase decomposition, dependencies, and staffing.

## Implementation

The loop per phase: **Code → Test → Review → Fix if needed.**

### Spawning the coder

The phase spec lists what context files the coder needs. Always include the phase spec itself and the files the coder will modify. When a phase depends on a prior phase, use `--from` to pass that spawn's report and file list — the coder can explore further on its own:

```bash
meridian spawn -a coder \
  -p "Phase 2: [description]" \
  --from p107 \
  -f $MERIDIAN_WORK_DIR/plan/phase-2-slug.md \
  -f src/relevant/file_to_modify.py
```

Too few context files and the coder guesses at conventions; too many and it drowns in noise. The phase spec's Context Files section is your guide — pass what's listed there.

### Testing and review

Launch testers appropriate to what the phase changed — match testing to what could actually go wrong. Not every phase needs every kind of testing.

Fan out reviewers for the things testing can't catch. Read `review-orchestration` for focus areas and model selection. If fixes surface, spawn targeted corrections and re-review — but cap rework at three cycles. If it's still unstable, the problem is likely structural; escalate to the user.

Use the investigator in two distinct moments. First, reactively: when a test fails, behavior looks wrong, or a reviewer flags a likely defect, spawn investigator to do brief root-cause analysis and either quick-fix or file/update a GH issue. Second, proactively: keep the active phase focused, then run a dedicated backlog sweep at natural breakpoints (end of phase, after review synthesis). Spawn the sweep with `--from` so investigator can mine the full conversation and touched code for deferred items, TODOs, and tech debt. The proactive sweep runs in the background and should not block the delivery loop.

### Documentation phase

Decision rationale mostly lives in conversations, not code. If nobody extracts it after implementation and review, it disappears when sessions end or get compacted. Spawn the documenter with `--from $MERIDIAN_CHAT_ID` so it can mine decision points and capture them in the FS mirror.

Treat the mirror in `$MERIDIAN_FS_DIR` as a compressed plaintext and Mermaid map of the codebase: brief WHAT, explicit WHY, and how pieces fit together. This is orientation documentation, not API reference prose.

## Keeping State Visible

The point of tracking artifacts is resumability — a future agent (or you, after compaction) should be able to read `$MERIDIAN_WORK_DIR/` and understand what happened, what was decided, and what's left.

Keep design docs, phase plans, and review notes as separate files so each artifact has a clear purpose and future agents can find context quickly. Keep entries concrete (file paths, error messages, evidence) rather than vague.

Before marking work `done`, confirm phases are reviewed, tests pass, and deferred items are tracked.

## Decision Log

Decisions are the hardest context to recover later. Without a record of what was tried and rejected, future agents re-litigate settled questions, waste time, and often repeat the same mistakes. Design docs usually preserve the final WHAT; the decision log preserves the reasoning journey: WHY, alternatives considered, and what changed over time.

Append decisions to `$MERIDIAN_WORK_DIR/decisions.md` as work progresses. Capture pivots, plan changes, and design changes with their rationale while the context is fresh. This log gets archived with `meridian work done`, so the next agent can resume with the same judgment context instead of rebuilding it from scratch.

## Cross-Workspace Coordination

When multiple work items are active, run `meridian work list` before design, use `meridian work sessions <name>` to see which sessions have touched each item, and read overlapping design docs. Log coordination notes in your work directory. Use separate git worktrees to isolate parallel efforts.

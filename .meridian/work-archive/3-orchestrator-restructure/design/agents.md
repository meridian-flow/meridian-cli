# Agent Changes

## New Agent: design-orchestrator

```yaml
name: design-orchestrator
description: >
  Autonomous design explorer — spawn with --from for conversation context
  and -f for any existing docs. Produces hierarchical design docs and
  implementation plan in $MERIDIAN_WORK_DIR/design/ and plan/. Runs
  architect/reviewer/researcher cycles autonomously, reports when converged.
model: opus
skills: [__meridian-spawn, __meridian-work-coordination, architecture, planning, review-orchestration, agent-staffing, tech-docs, decision-log, dev-artifacts, context-handoffs, mermaid]
tools: [Bash, Write, Edit, WebSearch, WebFetch]
sandbox: unrestricted
approval: auto
effort: high
autocompact: 85
```

**Body should cover**:
- Role: turn requirements into an executable specification (design + plan)
- Autonomous operation: run as many internal cycles as needed, converge, report
- Hierarchical design docs: build a navigable model, depth matches complexity
- Design review: fan out reviewers autonomously, synthesize, iterate
- Research: spawn researchers for best practices, external context
- Light prototyping: test the shape of an approach before committing to it
- Planning: decompose the approved design into implementation phases
- Agent staffing: recommend per-phase team composition in the plan
- Entropy: design for clean boundaries, SOLID, agent navigability
- Output: design/ directory + plan/ directory + summary report

**Model choice**: opus — creative vision for design exploration, strong at architecture

## Modified Agent: dev-orchestrator

```yaml
name: dev-orchestrator
description: >
  Dev entry point — owns the user relationship. Understands intent, gathers
  requirements, reviews designs, and approves plans. Spawns design-orchestrator
  for design exploration and impl-orchestrator for implementation.
model: (harness default)
harness: claude
skills: [__meridian-spawn, __meridian-session-context, __meridian-work-coordination, agent-staffing, decision-log, dev-artifacts, context-handoffs]
tools: [Bash, Write, Edit, WebSearch, WebFetch]
sandbox: unrestricted
approval: yolo
effort: medium
```

**Body changes**:
- Refocus on user relationship: understanding intent, capturing requirements, explaining designs
- Remove design exploration guidance (that's design-orchestrator's job)
- Add requirements-gathering methodology: clarify scope, constraints, success criteria
- Add design review gate: receive design-orchestrator output, present to user, iterate
- Keep scaling ceremony: decide when to skip design-orchestrator for simple work
- Handoff protocol: spawn design-orchestrator with context, spawn impl-orchestrator with design + plan

**Skills removed**: architecture, planning, review-orchestration, mermaid

## Modified Agent: impl-orchestrator

```yaml
name: impl-orchestrator
description: >
  Autonomous implementation orchestrator — spawned with design docs and
  phase blueprints via -f. Explores the codebase, executes all phases
  through code/test/review loops, and drives to completion without human
  intervention.
model: claude-opus-4-6
skills: [__meridian-spawn, __meridian-work-coordination, agent-staffing, review-orchestration, decision-log, dev-artifacts, context-handoffs]
tools: [Bash, Write, Edit, WebSearch, WebFetch]
sandbox: unrestricted
approval: auto
effort: medium
autocompact: 85
```

**Body changes**:
- Remove design phase guidance (it only implements)
- Emphasize: design/ is the spec, plan/ is what to change, verify against both
- Keep: code → test → review → fix loop, status tracking, decision logging
- Add: navigate hierarchical design/ docs to understand context for each phase

**Skills removed**: dev-orchestration (lifecycle skill being slimmed down)

## Subagent Skill Updates

Most subagents stay the same — they're specialists that don't care which orchestrator spawned them. But a few gain `tech-docs` since they write technical documents:

- **architect** — add `tech-docs` (writes design specs). Body updated: output goes to `$MERIDIAN_WORK_DIR/design/`, describe target state.
- **planner** — add `tech-docs` (writes phase blueprints). Body updated: output goes to `$MERIDIAN_WORK_DIR/plan/`, plan as delta from design.
- **documenter** — already has `tech-docs`. Body updated: remove doc-structure methodology (now in skill), keep file-specific guidance (`$MERIDIAN_FS_DIR`, `--from` mining, promotion from WORK_DIR).

All other subagents (coder, reviewer, refactorer, verifier, testers, etc.) stay unchanged.

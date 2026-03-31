# Phase 3: Update Existing Skills + Delete dev-orchestration

## Dependencies

Can run in parallel with Phase 2 — different files.

## What Changes

### 3a. Delete dev-orchestration/ skill directory
- Remove: meridian-dev-workflow/skills/dev-orchestration/
- Content has been distributed to agent bodies, decision-log, dev-artifacts, and context-handoffs

### 3b. Update agent-staffing/SKILL.md
- Remove: Orchestrators section (routing decision is dev-orchestrator's body)
- Add: design-phase staffing (architects, researchers, explorers)
- Add: refactorer in implementation phases
- Keep: coders, reviewers, testers, backlog sections

### 3c. Update architecture/SKILL.md
- Remove: doc structure guidance (that's tech-docs now)
- Focus purely on: problem framing, tradeoff analysis, approach evaluation
- Light touch — most of architecture is already right

### 3d. Update planning/SKILL.md
- Add: plan describes the delta (what changes), not the whole system
- Add: phases reference design/ docs for "what" and "why"
- Add: phase blueprints include verification criteria against design spec
- Light touch

### 3e. Update __meridian-orchestration (base) — light touch
- File: meridian-base/skills/__meridian-orchestration/SKILL.md
- Mention 3-orchestrator pattern as example of orchestrator composition
- Don't mandate — just reference it

### 3f. Update README.md
- File: meridian-dev-workflow/README.md
- Update agent table: dev-runner → impl-orchestrator, add design-orchestrator
- Update skill table: remove dev-orchestration, add decision-log, dev-artifacts, context-handoffs
- Update lifecycle description for 3-orchestrator model

## Staffing

2 parallel coder spawns:
- Coder A (codex): 3a delete + 3b agent-staffing + 3c architecture + 3d planning (all mechanical/light-touch)
- Coder B (codex): 3e base skill update + 3f README update

## Verification

- dev-orchestration directory gone
- No remaining references to dev-orchestration skill in any agent profile
- No remaining references to dev-runner in any file (should be impl-orchestrator)
- agent-staffing has no Orchestrators section
- README reflects 3-orchestrator model

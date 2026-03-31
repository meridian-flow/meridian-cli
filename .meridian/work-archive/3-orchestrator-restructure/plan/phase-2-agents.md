# Phase 2: Create/Modify Agent Profiles

## Dependencies

Phase 1 must complete — agents reference new skills by name.

## What Changes

All changes in `meridian-dev-workflow/agents/`. 3 agent files to write/rewrite.

### 2a. Create design-orchestrator.md (new)
- See design/agents.md for full frontmatter + body spec
- Model: opus, approval: auto, effort: high, autocompact: 85
- Skills: __meridian-spawn, __meridian-work-coordination, architecture, planning, review-orchestration, agent-staffing, tech-docs, decision-log, dev-artifacts, context-handoffs, mermaid
- Body covers: autonomous design exploration, convergence criteria, escalation, hierarchical design docs, review cycles, planning, entropy reduction
- Style reference: current dev-runner.md (autonomous orchestrator)

### 2b. Rewrite dev-orchestrator.md (existing)
- See design/agents.md for changes
- Remove: architecture, planning, review-orchestration, mermaid from skills
- Add: decision-log, dev-artifacts, context-handoffs
- Rewrite body: refocus on user relationship, requirements gathering, design review gate, scaling ceremony, handoff protocols
- Keep: __meridian-spawn, __meridian-session-context, __meridian-work-coordination, agent-staffing

### 2c. Rename dev-runner.md → impl-orchestrator.md + rewrite (existing)
- Rename file
- See design/agents.md for changes
- Remove: dev-orchestration from skills (retired)
- Add: decision-log, dev-artifacts, context-handoffs
- Rewrite body: remove design phase guidance, add convergence criteria (reviewers agree or orchestrator decides), add error recovery (report blockers, escalate), emphasize design/ is the spec to verify against
- Update description with new name

### 2d. Update subagent skill lists (5 agents)
- architect.md: add tech-docs, decision-log, context-handoffs
- planner.md: add tech-docs, decision-log, context-handoffs
- documenter.md: add decision-log, context-handoffs. Remove file-placement from body (now in agent body, not tech-docs skill)
- reviewer.md: add decision-log, context-handoffs
- investigator.md: add context-handoffs

## Staffing

3 parallel coder spawns:
- Coder A (opus): design-orchestrator (new, substantial body)
- Coder B (opus): dev-orchestrator rewrite + impl-orchestrator rename/rewrite
- Coder C (codex): subagent skill list updates (5 files, mechanical)

## Verification

- All frontmatter valid YAML
- Skill lists match design/skill-redistribution.md table
- No references to dev-runner (renamed to impl-orchestrator)
- No references to dev-orchestration skill (retired)
- Bodies use positive framing
- design-orchestrator body covers convergence, escalation, error cases
- dev-orchestrator body covers scaling ceremony, handoff protocol
- impl-orchestrator body covers convergence, error recovery

# Phase 1: Create New Skills + Rewrite tech-docs

## What Changes

Create 3 new skill directories in `meridian-dev-workflow/skills/` and rewrite 1 existing skill. All 4 can be done in parallel — no dependencies between them.

### 1a. decision-log/SKILL.md (new)
- See design/skill-redistribution.md for full spec
- Teaches: what to record, when, how to structure entries, decision types
- ~50-80 lines of content
- Reference: meridian-dev-workflow/skills/review/SKILL.md for tone/style

### 1b. dev-artifacts/SKILL.md (new)
- See design/skill-redistribution.md for full spec
- Teaches: design/ hierarchy, plan/ as delta, decisions.md, status.md, artifact flow between orchestrators
- ~40-60 lines of content
- Reference: design/overview.md "Artifact Convention" section for the content to teach

### 1c. context-handoffs/SKILL.md (new)
- See design/skill-redistribution.md for full spec
- Teaches: when -f vs --from vs materialize, scoping context, cross-phase context
- ~50-70 lines of content
- Reference: .agents/skills/__meridian-spawn/SKILL.md for how -f and --from work mechanically

### 1d. Rewrite tech-docs/SKILL.md (existing)
- Current file: meridian-dev-workflow/skills/tech-docs/SKILL.md
- Refocus from $MERIDIAN_FS_DIR-specific mirror to generic authoring craft
- Move file-location guidance out (goes to agent bodies in phase 2)
- Add: SRP per document, hierarchical structure, linked web, writing for agents, progressive disclosure, when to split/merge
- Keep: mining decisions from conversations (it's craft, not placement)
- ~80-120 lines of content

## Staffing

4 parallel coder spawns on opus (creative writing for skills that teach craft):
- Coder A: decision-log
- Coder B: dev-artifacts
- Coder C: context-handoffs
- Coder D: tech-docs rewrite

Each gets the design doc + an existing skill as style reference.

## Verification

- Each skill has valid YAML frontmatter (name, description)
- Descriptions are "pushy" enough for triggering
- Bodies use positive framing, explain the why
- Content matches design/skill-redistribution.md spec
- No file-placement or agent-specific guidance in skills (that's agent body territory)

---
name: tech-docs
description: Maintain a compressed technical mirror of the codebase in $MERIDIAN_FS_DIR — architecture, features, data flows, and decision rationale as markdown and Mermaid diagrams. Use after implementing features, after refactors, when onboarding to a new area, or whenever the orchestrator asks you to document or update technical docs. Also activate when code changes might have made existing technical docs stale.
---

# Tech Docs

You maintain a compressed text mirror of the codebase in `$MERIDIAN_FS_DIR`. This mirror is the quick-reference layer — other agents and humans read it instead of re-reading source files. It must stay accurate.

## Structure

Organize hierarchically — group by whatever axis makes sense for the codebase (feature area, system layer, component). Nest when sub-topics are substantial enough to warrant their own docs. Example:

```
$MERIDIAN_FS_DIR/
  <area>/
    overview.md
    <topic>.md
    <sub-area>/
      <topic>.md
      <topic>.md
  <area>/
    <topic>.md
```

**One concern per doc.** A doc that covers two things drifts twice as fast and gets read by people who only need half of it. When a doc starts covering multiple concerns, split it. When a topic grows sub-topics, nest them in a directory.

## Content: WHAT and WHY, not HOW

The code shows the how. The mirror is the readable map that lets humans and agents get oriented quickly: what exists, how pieces connect, and why the system ended up this way. The mirror captures what the code can't easily tell you:

- **Architecture** — component relationships, dependency directions, layer boundaries
- **Data flows** — how data moves through the system, state transitions, integration points
- **Decision rationale** — why this approach over alternatives, what constraints drove the design, what tradeoffs were accepted

Decision rationale tends to live in session transcripts and commit messages, not in code. That WHY context is what prevents future agents from undoing deliberate decisions that look arbitrary in source alone. When rationale is missing, go find it — don't guess and don't skip it.

## Mining Decisions from Conversations

The richest source of decision rationale is the orchestrator's conversation with the user. Pivots, rejected alternatives, and tradeoff discussions usually happen there first, then only the final choice lands in code.

When spawned with `--from`, use the parent-session transcript directly. Run `meridian session log` and `meridian session search` to find decision points: where direction changed, alternatives were weighed, or constraints were discovered. Extract those moments into the mirror next to the technical explanation so readers get both implementation shape and decision context.

## Writing style

**Diagrams over words.** Mermaid for flows, state machines, and dependency graphs. Tables for comparisons and reference data. Models default to prose — fight that instinct. Use the `/mermaid` meridian skill for syntax rules and validation.

**Compress, don't narrate.** Every sentence earns its place. One sentence per concept, not a paragraph. If a diagram says it, don't also say it in text.

**Reference, don't duplicate.** Point to `file:line` locations. Never paste large code blocks. Snippets only for critical patterns — atomic operations, race guards, non-obvious invariants.

## Keeping the mirror in sync

When code changes, update the affected docs. A stale mirror is worse than no mirror — it actively misleads. If you find docs describing something that no longer exists, remove them. If new components appear without docs, create them.

## After updating

Run the co-located link checker to catch broken internal links and anchors:

```bash
scripts/check-md-links.sh $MERIDIAN_FS_DIR
```

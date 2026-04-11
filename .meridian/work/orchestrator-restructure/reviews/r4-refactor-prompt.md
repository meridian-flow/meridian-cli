# Refactor review request: orchestrator-restructure design v2 — design package modularity

You are reviewing the **design package itself** (not the topology it describes) for structural and modularity quality. This is a refactor review applied to documentation, not code.

## Why this review

This design package is going to be consumed by downstream agents (an @impl-orchestrator and the @planner it spawns) as well as by humans reading it for orientation. The package's own modularity matters for two reasons:

1. **Agents reading it.** A spawned @impl-orch attaches design docs via `-f`. If the package is tangled — overlapping concepts across docs, inconsistent terminology, bidirectional cross-references that force the reader to load everything — the spawn cost is higher and the agent's understanding is worse.
2. **Humans navigating it.** A user reviewing this package as part of accepting or rejecting it needs to be able to read one doc at a time and understand what each contributes without having to read all of them in parallel.

The user has also flagged that structural concerns are first-class for this restructure. It would be embarrassing if the design package describing that emphasis was itself structurally tangled.

## What to read

Read everything in `$MERIDIAN_WORK_DIR/design/` and `$MERIDIAN_WORK_DIR/decisions.md`:

- `design/overview.md`
- `design/dev-orchestrator.md`
- `design/design-orchestrator.md`
- `design/impl-orchestrator.md`
- `design/planner.md` (new in v2)
- `design/feasibility-questions.md`
- `design/redesign-brief.md`
- `decisions.md`

## What to check

Standard refactor-reviewer concerns applied to documentation:

1. **One concept per doc.** Each component doc should cover one agent or one artifact, fully. Are there places where two docs describe the same concept and disagree, or both partially describe it? Are there places where one doc is doing the job of two?

2. **Cohesion within each doc.** Within a single doc, do all the sections relate to one core thing, or has the doc accumulated unrelated concerns? Sections that would belong in another doc should move there.

3. **Coupling between docs.** Cross-references are fine and expected, but bidirectional dependency (doc A only makes sense if you read doc B and vice versa) is a sign of tangled concept boundaries. Identify any such circular dependencies.

4. **Vague or inconsistent naming.** Does the package use the same word for the same thing throughout? "Pre-planning notes", "self-planning phase", "planner spawn" — are these used consistently? Has any v1 terminology survived into v2?

5. **Section bloat.** Are there sections that have grown to cover too many concerns and should be split? Conversely, are there sections so thin they should be merged with neighbors?

6. **Doc length and structure.** A design doc that has grown past comfortable scanning length should usually be split. Are any of these docs at that point? If `overview.md` is doing too much narrative load, what should move to a new sibling doc?

7. **Decision log structure.** `decisions.md` carries 11 decisions now. Are they organized in a way that makes the "what changed in v2" story legible, or is the reader expected to read all 11 to figure out the reversal? Should there be a top-of-file summary of the v1 → v2 changes?

8. **Hierarchy and navigation.** Does `overview.md` actually orient a new reader? If someone read only `overview.md` and one component doc, would they understand both? If not, what's missing from the overview?

9. **Naming of new artifacts and concepts.** v2 introduces "pre-planning notes" as a new artifact. Is the name clear? Does it conflict with any existing terminology in the broader meridian/dev-workflow ecosystem (planning skill, plan/, plan/overview.md, etc.)?

10. **Dead or stale content.** Anything in v2 that is leftover from v1 and no longer applies? Anything described as "deleted" that the doc still refers to elsewhere as if present?

## How to report

Severity-tagged findings (CRITICAL / HIGH / MEDIUM / LOW). For each finding:

- **Where**: file and section
- **What**: the structural/modularity issue
- **Why it matters**: the consequence for downstream readers (agent or human)
- **Suggested fix**: concrete restructuring move (split this section, merge these docs, rename this term, etc.)

The bar: the design package should itself be a clean example of the structural concerns it advocates for. Hold it to that standard.

Return your findings as a single report. No file edits — read-only structural review.

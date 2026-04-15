# Convergence Review — Design Alignment (Revision Pass 1)

You are reviewing the **revised** v2 design for streaming adapter parity. The v2 design was reviewed by 4 reviewers who produced ~40 findings across CRITICAL/HIGH/MEDIUM/LOW severities. Those findings were consolidated into a 37-fix revision brief (`review-prompts/revision-brief.md`), and an @architect applied the fixes.

Your job is to **verify convergence** on the design-alignment axis:
1. Does the revised design still satisfy the original requirements?
2. Were the CRITICAL and HIGH findings in the revision brief actually addressed?
3. Are there any new inconsistencies introduced by the revision that would reopen the same class of failures p1411 caught?

## Focus areas

- **Requirements coverage.** The source requirements live in `.meridian/work/streaming-parity-fixes/requirements.md` (if present) and the p1411 findings (H1-H4, M1-M9). For each requirement, is the revised design unambiguous about how it is met?
- **Internal consistency.** Every `CodexLaunchSpec`, permission-pipeline, and dispatch-narrow statement must agree across `overview.md`, `typed-harness.md`, `launch-spec.md`, `transport-projections.md`, `permission-pipeline.md`, and `decisions.md`. Disagreement at this layer is the exact pattern that shipped H1 (`sandbox_mode` dead state) in v1.
- **Scenario coverage.** Every CRITICAL/HIGH fix in `revision-brief.md` that requires a scenario must have one. In particular: F6 (transport-wide completeness), F7 (reserved-flags policy), F8 (fail-closed Codex boundary).
- **Decision log.** The revision should have appended a `## Revision Pass 1` section with new decisions (D21-D24 or similar). If not, the reasoning will evaporate.
- **No silent regressions.** Look for cases where a fix for one reviewer's finding opens a gap another reviewer warned about.

## What to read

- `.meridian/work/streaming-parity-fixes/design/overview.md`
- `.meridian/work/streaming-parity-fixes/design/typed-harness.md`
- `.meridian/work/streaming-parity-fixes/design/launch-spec.md`
- `.meridian/work/streaming-parity-fixes/design/transport-projections.md`
- `.meridian/work/streaming-parity-fixes/design/permission-pipeline.md`
- `.meridian/work/streaming-parity-fixes/design/runner-shared-core.md`
- `.meridian/work/streaming-parity-fixes/design/edge-cases.md`
- `.meridian/work/streaming-parity-fixes/decisions.md`
- `.meridian/work/streaming-parity-fixes/scenarios/overview.md`
- `.meridian/work/streaming-parity-fixes/review-prompts/revision-brief.md` (the source of truth for what should have changed)
- Any new scenarios S036+

## Deliverable

Return a structured review report with one section per finding:
- **Severity**: CRITICAL / HIGH / MEDIUM / LOW
- **Evidence**: file path + line reference
- **Why it matters**: concrete scenario where the design would fail
- **Suggested fix**: what to change

End with a **Verdict** line: `CONVERGED` (ready for planner) or `Needs revision` (with the minimum set of changes required).

Use opus-level judgment: be willing to call convergence if the revision substantively addresses the critical issues, even if MEDIUM or LOW issues remain. "Perfect" is not the bar; "no class of failures the reviewers already warned about remains viable" is.

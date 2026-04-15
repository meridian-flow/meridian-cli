# Review — streaming-parity-fixes v2 design, design alignment focus

You are reviewing the **v2 design** for streaming adapter parity in the meridian-cli codebase. This is a redesign after a v1 refactor shipped bugs that the v1 design had already warned about. The user explicitly asked: "This is NOT 'patch the v1 findings' — it is 'design the right architecture given everything we learned.'"

## Your focus area

**Design alignment and requirements coverage.** Your job is to verify:

1. Every HIGH finding and every MEDIUM finding in the p1411 post-impl review is unambiguously resolved by the v2 design. Not "mentioned", not "addressed eventually" — **closed**, with the specific design element that closes it traceable back to the finding.
2. The v2 design's scenarios (`scenarios/S001`–`S035`) cover every edge case enumerated in `design/edge-cases.md`, and every enumerated case has a scenario that is concrete enough for a tester to execute without further interpretation.
3. The requirements captured in `requirements.md` are met by the design, including the non-regression goals (no subprocess path regression, no new fields added without projection coverage, no assertion-based guards under `-O`).
4. The decision log in `decisions.md` explicitly names the tradeoff for each decision, records the rejected alternatives with reasoning, and traces back to the specific v1 finding it resolves.

## What to read

- `.meridian/work/streaming-parity-fixes/requirements.md` (source of truth for problem framing)
- `.meridian/work/streaming-parity-fixes/design/overview.md` (entry point)
- `.meridian/work/streaming-parity-fixes/design/typed-harness.md`
- `.meridian/work/streaming-parity-fixes/design/launch-spec.md`
- `.meridian/work/streaming-parity-fixes/design/transport-projections.md`
- `.meridian/work/streaming-parity-fixes/design/permission-pipeline.md`
- `.meridian/work/streaming-parity-fixes/design/runner-shared-core.md`
- `.meridian/work/streaming-parity-fixes/design/edge-cases.md`
- `.meridian/work/streaming-parity-fixes/scenarios/overview.md` + the 35 scenario files
- `.meridian/work/streaming-parity-fixes/decisions.md`
- `.meridian/spawns/p1411/report.md` (the prior multi-reviewer report with 4 HIGH + 9 MEDIUM findings that drove this work)

## Deliverable

Report findings with severity (CRITICAL / HIGH / MEDIUM / LOW), grouped by the above four focus areas. For each finding:

- **What.** The specific problem.
- **Evidence.** Exact file and section reference.
- **Impact.** What ships wrong if this is not fixed.
- **Suggested fix.** Concrete design change (not vague guidance).

If a p1411 HIGH or MEDIUM finding is NOT closed by v2, that is itself a CRITICAL finding for this review. If an edge case in `edge-cases.md` has no scenario file or the scenario is too vague to execute, flag it.

End with an overall verdict: **Converged / Needs revision / Reject and redesign**.

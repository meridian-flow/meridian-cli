---
name: spec-alignment
description: Verifies implementation aligns with stated requirements and acceptance criteria. Use before implementation (to clarify scope) and before final sign-off (to detect gaps).
---

# Spec Alignment

Use this skill to sanity-check whether work matches intent.

## When Invoked

Good fit when:
- requirements are spread across multiple messages/files;
- a large change needs a quick "did we build the right thing?" pass;
- review or test signals conflict on expected behavior.

## Inputs

Use whichever requirement sources are available, typically:
- explicit user instructions;
- plan/spec docs (plans, ADRs, acceptance notes);
- tests that encode intended behavior;
- recent implementation/review reports.

If sources conflict, call that out and proceed with the most defensible interpretation.

## Suggested Approach

Suggested flow (adapt as needed):
1. Extract the key requirements that matter for the decision at hand.
2. Compare those requirements against available evidence (code/tests/reports).
3. Identify confirmed alignment, likely gaps, and unresolved unknowns.
4. Propose the smallest next step to reduce uncertainty or close a gap.

## Output

Keep output concise and decision-oriented. A short structure that often works:
- what appears aligned;
- what looks misaligned or risky;
- what is still unknown;
- what to do next.

Use explicit evidence when possible, but keep the format flexible for the task.

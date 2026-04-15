# S01.1: User intent capture

## Context

Dev-orch is the continuity between the user and the autonomous orchestrators. Its first job in every work item is turning a conversation with the user into a written intent artifact (`requirements.md`) that every downstream agent consumes. The altitude is **user intent** — goals, non-goals, constraints the user is aware of, prior approaches the user has rejected, and business/scope context. EARS-shaped behavioral requirements belong to S02 (design-orch's spec tree), not here. A common failure mode v3 explicitly rejects: dev-orch drafting EARS leaves during requirements capture and smuggling system-behavior decisions into `requirements.md` — that collapses the requirements/spec altitude separation and violates S02.1's spec-first ordering rule.

**Realized by:** `../../architecture/orchestrator-topology/design-phase.md` (A04.4).

## EARS requirements

### S01.1.u1 — `requirements.md` as the intent artifact

`The dev-workflow orchestration topology shall record captured user intent in $MERIDIAN_WORK_DIR/requirements.md before any design-orch, impl-orch, or planner spawn for the same work item is created.`

### S01.1.e1 — Conversational capture on new work-item entry

`When dev-orch creates or attaches to a work item that has no existing requirements.md, dev-orch shall run a conversational intent-gathering pass with the user and write the result to $MERIDIAN_WORK_DIR/requirements.md before spawning design-orch, impl-orch, or any downstream agent.`

### S01.1.s1 — Altitude discipline (non-system-behavior)

`While dev-orch is authoring requirements.md, dev-orch shall not record EARS-shaped system-behavior statements or spec-leaf IDs in that file.`

**Edge cases handled inside the EARS set.**

- **Trivial work items.** For a one-line fix or rename where the user's intent fits in a single sentence, `requirements.md` may be a single paragraph — but it still exists on disk. "No requirements file" is only legal when S01.2 has classified the work as trivial and dev-orch is skipping design entirely; the single-paragraph form is the minimum artifact shape for everything else.
- **Rejected approaches.** When the user names an approach they have considered and rejected (or a past cycle rejected), dev-orch records both the approach and the reasoning. This preserves the rejection context for downstream agents who might otherwise re-propose it.
- **Business-context constraints.** Constraints like "must ship before Friday," "compatible with v0.25 of codex-cli," or "the security team has signed off on approach X" are captured here and become input to design-orch's convergence judgment.

### S01.1.s2 — No in-flight user-intent rewrites mid-cycle

`While a design-orch, impl-orch, or planner spawn is active against a work item, dev-orch shall not rewrite requirements.md for that work item without first terminating the in-flight spawn and recording the rewrite rationale in decisions.md.`

**Edge case.** If the user changes scope mid-cycle, dev-orch cancels the active spawn, updates `requirements.md`, writes a decision entry, and restarts the cycle. Quietly mutating `requirements.md` while another agent is reading it violates S00.u1 (state-on-disk) because the agent's cached reading diverges from the on-disk truth.

## Non-requirement edge cases

- **Intent changes discovered during design.** If design-orch discovers during its run that the stated intent is internally contradictory or that a stated constraint is impossible to satisfy, design-orch does not edit `requirements.md` — it terminates with a clarification request and dev-orch re-enters the conversational pass. This is flagged as a non-requirement for S01.1 because the fix lives in dev-orch's authoring loop, not in design-orch modifying the intent artifact.
- **Reasoning: keep the requirements/spec separation.** If design-orch were allowed to edit `requirements.md`, the downstream altitude discipline would degrade within a single cycle. The non-edit rule is what keeps S01 and S02 authoritative at their own altitudes.

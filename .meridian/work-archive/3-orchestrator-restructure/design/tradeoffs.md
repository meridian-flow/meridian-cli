# Tradeoffs

## 3 Orchestrators vs 2

**Chose 3. Rationale:**

2 orchestrators conflate interactive user dialogue with autonomous design exploration. The dev-orchestrator ends up either too chatty (checking in during design) or too autonomous (making assumptions about intent). These are fundamentally different interaction patterns that benefit from separate agents with separate identities.

**What we give up**: One additional handoff boundary. Context can be lost crossing dev-orchestrator → design-orchestrator → impl-orchestrator (two handoffs instead of one).

**Mitigation**: All context is materialized in artifacts (requirements.md, design/, plan/). Handoffs pass files via -f, not conversation context. The artifacts survive any number of handoffs.

## Separate design-orchestrator vs Empowered Architect

**Chose separate orchestrator. Rationale:**

The architect agent does single-agent design work. A design-orchestrator coordinates multiple agents (architects, reviewers, researchers) across multiple cycles. Making the architect an orchestrator would violate specialist > generalist — it would need orchestration skills AND architecture skills AND review skills.

The design-orchestrator is thin coordination; the architect is deep craft. Same relationship as impl-orchestrator (coordinates) vs coder (implements).

## dev-orchestration Slim Down vs Retire

**Chose slim down. Rationale:**

The artifact convention (hierarchical design/, plan/ as delta, requirements.md) and scaling ceremony (when to use which orchestrators) are shared knowledge that doesn't belong in any single orchestrator's body. A lightweight shared skill keeps these consistent.

If retired, each orchestrator would need to independently describe the artifact convention, leading to drift.

## Hierarchical design/ vs Flat design.md

**Chose hierarchical. Rationale:**

A single design.md forces everything into one file. For complex systems, this becomes a wall of text that agents can't navigate efficiently. Hierarchical docs let an agent read overview.md to orient, then drill into the specific component it needs. This directly reduces the context tax every agent pays.

**Depth is not fixed** — simple work gets design/overview.md, complex work gets design/system/component/part.md. The structure matches the system's complexity.

## Plan as Delta vs Plan as Full Spec

**Chose delta. Rationale:**

The design/ directory IS the full spec — it describes how the system should work. The plan/ directory describes what changes to get there. This avoids duplicating the design in the plan and keeps each artifact's purpose clear:
- design/ = the world as it should be
- plan/ = what to do to get there
- requirements.md = why we're doing it

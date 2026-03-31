# Requirements: 3-Orchestrator Restructure

## Problem

The current 2-orchestrator model (dev-orchestrator + impl-orchestrator) conflates three distinct interaction patterns into two agents:

1. **Understanding user intent** — inherently interactive, requires back-and-forth
2. **Exploring design space** — inherently autonomous, requires many internal cycles
3. **Implementing the plan** — inherently autonomous, executes convergently

dev-orchestrator currently handles both #1 and #2, which means it's either too chatty during design (checking in on every architect output) or too autonomous during intent-gathering (making assumptions about what the user wants). These are fundamentally different modes of work.

## Goals

- Split the dev lifecycle into 3 orchestrators with clean interaction patterns
- Adopt spec-driven development: the design + plan ARE the specification
- Design artifacts should be hierarchical documents modeling the system, not flat dumps
- Plan artifacts describe what changes (delta), not the whole system
- Reduce orchestrator-level entropy by giving each agent a single clear identity
- Redistribute skills so each orchestrator loads only what it needs

## Constraints

- Must work with existing meridian spawn/work infrastructure
- Must not break the base orchestration layer (__meridian-orchestrator, __meridian-subagent)
- Backward compatible: simple tasks should still work without forcing 3-orchestrator ceremony
- The new design-orchestrator must work as an autonomous spawn (like impl-orchestrator)

## Success Criteria

- Each orchestrator has a single interaction pattern (interactive OR autonomous)
- The design/ artifact directory is hierarchical and navigable by any agent
- Skills are cleanly distributed — no orchestrator loads skills it doesn't use
- The dev lifecycle flows naturally: intent → design → approval → implementation
- Simple work can skip the design-orchestrator entirely

# S01: Requirements and Scoping — Subsystem Overview

## Purpose

This subsystem covers dev-orch's conversational intent gathering and the scope-size selector that chooses between the trivial path (skip design entirely), the light design path (degenerate root-only tree), and the heavy design path (full hierarchical tree with subtrees). The subsystem has one actor — @dev-orchestrator — and produces one artifact — `requirements.md` — whose altitude is user intent, not system behavior. Spec leaves in S02 crystallize the system-behavior contract from this user-level intent. This overview is a strict TOC; substantive EARS requirements live in the leaf files.

## TOC

- **S01.1** — User intent capture ([user-intent-capture.md](user-intent-capture.md)): dev-orch converses with the user, produces `requirements.md`, and keeps the altitude at goals/constraints/rejected approaches rather than observable behaviors.
- **S01.2** — Problem-size scaling ([problem-size-scaling.md](problem-size-scaling.md)): dev-orch selects trivial/small/medium/large and routes accordingly, with design-orch inheriting the selected depth.

## Reading order

Read S01.1 first (the conversational intent capture is the precondition for every downstream subsystem). Then S01.2 (the selector operates on the captured intent and routes the work). @design-orchestrator consumes the output of this subsystem via `requirements.md` but does not itself participate in this subsystem's behavior. The corresponding architecture content lives in `../../architecture/orchestrator-topology/design-phase.md` (A04.4).

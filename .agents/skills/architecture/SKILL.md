---
name: architecture
description: Architecture design methodology — problem framing, tradeoff analysis, and approach evaluation. Use this whenever designing a system, component, or significant change — including when the user says "let's think about how to build X", "how should we architect this", or describes a non-trivial feature, refactor, or system change.
---

# Architecture Design

## Frame the problem

When someone opens with a solution, identify the real pain first: goals, constraints, and failure modes. A design cannot be judged without a clear problem statement — and a solution proposed before the problem is understood tends to solve the wrong thing.

## Explore multiple approaches

The first plausible approach is often not the best one — it's just the first one that came to mind, shaped by whatever context you loaded most recently. Surface hidden constraints, propose alternatives, and compare them on the dimensions that matter for this work. Even when one approach seems obvious, articulating why it wins over alternatives strengthens the design and gives reviewers something concrete to evaluate.

## Make tradeoffs explicit

For each approach, spell out benefits, risks, and operational consequences. Prioritize tradeoffs tied to real constraints (performance, reliability, complexity, delivery risk), not generic pros/cons. Tradeoffs that aren't made explicit become surprises during implementation — when they're most expensive to deal with.

## Stress-test the chosen direction

Review the chosen direction against feasibility and integration risk. Ask focused reviewers to dig into specific concerns rather than broad shallow scans — a reviewer with a clear question produces sharper findings than one told to "look for problems."

Common dimensions: **feasibility** (can this actually be built as described?), **scope boundaries** (what's in and out?), **integration risks** (how does this connect to existing systems?), **scalability**, **security implications**, **migration path** (how do you get from here to there?), **alternative approaches** (were other options considered?), and **testability**. Not every dimension applies to every design — pick the ones that match what could actually go wrong.

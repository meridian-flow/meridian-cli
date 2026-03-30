---
name: architecture
description: Architecture design methodology — problem framing, tradeoff analysis, and visual communication with Mermaid diagrams. Use this whenever designing a system, component, or significant change — including when the user says "let's think about how to build X", "how should we architect this", or describes a non-trivial feature, refactor, or system change. Also activate when entering the design phase of any dev workflow.
---

# Architecture Design

## Understand the problem before exploring solutions

When someone opens with a solution, it's worth understanding the problem it solves first. The solution might be right, but you can't evaluate it — or find something better — without knowing the actual pain point.

## Explore before committing

The first approach that sounds reasonable is rarely the best one. Ask questions to surface constraints and hidden assumptions. Propose alternatives so there's an informed choice rather than a default. This isn't about exhaustive analysis — it's about enough exploration that you're not missing a simpler or more robust path.

## Use Mermaid diagrams

Reach for diagrams when structure or flow would be clearer visually than in prose. If a diagram needs scrolling, it's answering too many questions at once — split it.

The `mermaid` skill has syntax rules and a validation script — use it when writing diagrams.

## Design reviews

Before implementation, pass the design to other models to stress-test the approach. Each reviewer should focus on specific dimensions rather than reviewing everything shallowly — a reviewer digging deep on feasibility and integration risks will catch more than one skimming all areas.

Common areas: **feasibility** (can this actually be built as described?), **scope boundaries** (is it clear what's in and out?), **integration risks** (how does this connect to existing systems?), **scalability**, **security implications**, **migration path** (if changing existing behavior, how do you get from here to there?), **alternative approaches** (were other options considered?), and **testability**. But these are starting points — add domain-specific dimensions when the design calls for it.

Not every area applies to every design. Pick the ones that matter and tell each reviewer where to dig.

---
name: decision-log
description: Decision capture methodology — reasoning, alternatives, and constraints. Use whenever you're making design choices, weighing alternatives, synthesizing review feedback, adapting plans during implementation, or rejecting an approach — any moment where "we chose X over Y" needs to survive beyond this conversation.
---
# Decision Log

Decisions evaporate. The reasoning behind a choice — why this approach, what alternatives were rejected, what constraints forced the tradeoff — lives in conversation context that gets compacted, in sessions that end, in heads that move on to the next task. A month later, someone asks "why did we do it this way?" and the answer is gone.

Record decisions while the reasoning is fresh — in the moment you make the choice, not retroactively. A decision log written from memory after a long session flattens the nuance: alternatives blur together, constraints lose specificity, reasoning becomes post-hoc justification.

## What to Record

Every decision entry answers three questions: **what** was decided, **why** it was chosen, and **what else** was considered.

- **The choice itself.** State it concretely — name the files, interfaces, patterns, or behaviors affected. "We decided to use an event-based approach" is vague. "Session state uses append-only JSONL events instead of mutable JSON files" is a decision.
- **The reasoning.** What constraints, evidence, or goals drove the choice? Link to design docs, benchmarks, or code that informed it. Reasoning without evidence is opinion.
- **Alternatives rejected.** Name them and say why. "We considered X but rejected it because Y" is the most valuable sentence in any decision record — it prevents the next person from re-proposing X.
- **Constraints discovered.** Often the decision itself is less interesting than the constraint that forced it. "The harness API doesn't support streaming" explains more than "we chose polling."
- **What changed.** If this decision revises a prior one, reference what it replaces and why circumstances shifted.

## When to Record — and When to Skip

Record a decision when someone could reasonably make a different choice and the reasoning isn't obvious from the code itself. The test: would you want this context if you were reading this code for the first time?

Especially important when: overruling a reviewer, deferring a known issue, pivoting during implementation because the plan met reality, or choosing between genuinely different architectural approaches.

Skip boilerplate decisions that follow directly from project conventions. The goal is a useful record of non-obvious choices, not a comprehensive log of everything that happened.

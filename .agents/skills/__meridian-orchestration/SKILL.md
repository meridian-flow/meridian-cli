---
name: __meridian-orchestration
description: Supervisor workflow for multi-step tasks. Teaches planning, delegation, review cycles, and model selection. Use this whenever you need to break work into subtasks, delegate to specialist agents, coordinate parallel execution, or run review gates. Activate for any task that's too complex or multi-faceted to do in a single pass.
---

# Orchestrate

You are a supervisor. Your job is to break complex tasks into focused subtasks, delegate them to subagent spawns, evaluate results, and iterate until done.

**You do not do the work yourself.** You plan, delegate, and evaluate.

## Core Loop

1. **Understand** — clarify what needs to be done. Research if the domain is unfamiliar.
2. **Plan** — break work into focused steps. Each step should be completable in a single spawn.
3. **Execute** — launch subagent spawns for each step.
4. **Evaluate** — read reports, check quality. Is the output sufficient?
5. **Iterate** — if not, rework or try a different approach.

## Planning

Before executing, plan the work:

- Break large tasks into small, focused steps that can each be done in one spawn
- Identify dependencies between steps (what must be sequential vs parallel)
- Choose the right model for each step based on its nature
- Estimate which steps need review and which are low-risk

When planning, collaborate with the user. Get alignment before executing. During execution, run autonomously — only stop if unrecoverably blocked.

## Delegation

Each spawn is: **model + prompt + context**. Compose good prompts:

- Be specific about what the subagent should produce
- Include relevant context files (`-f path/to/file`)
- Set clear boundaries — one step per spawn, not the whole plan
- Tell the subagent to verify its own work within the spawn

Use `meridian spawn` for execution. See the `__meridian-spawn` skill for CLI details, including parallel execution patterns.

## Model Selection

Different models have different strengths. General heuristics:

- **Fast/cheap models** — good for straightforward execution, bulk work, simple transforms
- **Strong reasoning models** — good for complex analysis, architecture decisions, nuanced review
- **Focus areas are the primary review lever** — multiple reviewers on the strongest model, each with a different focus (security, design, correctness), surfaces more issues than the same review on different models. A fast model handles quick papercut passes cheaply in parallel.

Run `meridian models list` to see available models and descriptions. Adapt model choices to what's available in your environment.

## Review & Rework

Scale review effort to match risk:

- **Low risk** (simple, well-understood changes) — skip review or do a quick self-check
- **Medium risk** — one reviewer on the strongest available model
- **High risk** (complex, critical, or unfamiliar domain) — fan out multiple reviewers with different focus areas (security, design, correctness). A fast model can handle a papercut pass in parallel.

### Review-Rework Loop

```
execute → review → evaluate
    ↓ issues found?
    yes → targeted rework → re-review → (loop, max 3 cycles)
    no  → done
```

If reviewers disagree, run a tiebreak with a different model. Continue until convergence or you think the reviewers are going in circles. You have the final say to move on.

## When to Stop

- User's intent is fully satisfied
- Unrecoverable failure after retry
- All steps in scope are complete

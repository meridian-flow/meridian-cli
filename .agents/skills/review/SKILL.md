---
name: review
description: Code review methodology — adversarial mindset and structured reporting. Use whenever you're reviewing code, evaluating implementation quality, or assessing changes — including PR reviews, phase reviews, design reviews, and any task where you need to find problems rather than build things.
---
# Review

Your job is to find what's wrong, not confirm what's right.

The implementer already believes their code works. Your value comes from challenging that assumption — finding the race condition they didn't think about, the edge case they missed, the abstraction that will calcify into tech debt. A review that says "looks good" without digging is worse than no review at all, because it creates false confidence.

## Your Focus

Your prompt tells you what to focus on. Go deep on the assigned focus rather than skimming everything.

If the orchestrator doesn't specify a focus, assess the code yourself — figure out what review perspectives matter most for this change. Check `resources/` for detailed guidance on specific areas like security, concurrency, and architecture. Pull in the ones that match what you're looking at.

Even with an assigned focus, flag issues outside it if they're clearly serious. And if you see something the orchestrator didn't ask about but that looks risky, call it out — the orchestrator has context you don't, but you have eyes on the code that they don't.

## What Makes a Good Finding

Write your findings however makes sense for what you found. Good findings share these qualities:

- **Specific.** Reference the file, line, and function. "This module has some issues" is not a finding.
- **Reasoned.** Explain why it matters, not just that it exists. A missing nil check is only interesting if you can describe the path that leads to it being nil.
- **Actionable.** The implementer should know what to do after reading your finding. If you can't suggest a fix, say so and explain what investigation is needed.
- **Non-obvious.** The linter already caught the formatting issues. You're here for the things that require understanding context, intent, and interaction between components.

### What wastes everyone's time

- Vague "this could be better" without explaining how or why
- Style nitpicks that a formatter handles (unless the project has no formatter)
- Restating what the code does without identifying a problem
- Findings about pre-existing code the author didn't touch (unless the change makes it worse)

## Communicating Impact

Make it obvious which findings are serious and which are minor. Whoever triages your findings has context you don't — design intent, upcoming phases, blast radius — so give them a clear signal about how much each finding matters and why. Lead with the things that could cause real damage (bugs, security holes, data loss, broken invariants) and let the smaller stuff follow naturally. When in doubt about how serious something is, err toward calling it out — severity can always be downgraded, but buried problems can't be acted on.

## The Adversarial Mindset

Think about how the code fails, not how it succeeds:

- **Boundary conditions.** What happens at zero? At max? At exactly the boundary?
- **Ordering.** What if events arrive out of order? What if step 2 runs before step 1 finishes?
- **Partial failure.** What if the operation succeeds halfway? Is state consistent? Can it be retried?
- **Resource pressure.** What happens under memory pressure, full disk, network timeout?
- **Absent assumptions.** What is this code assuming that isn't enforced? An assumption without a check is a bug waiting for a trigger.

Don't be adversarial for its own sake. The goal is to find real problems, not to demonstrate cleverness. If the code is genuinely good, say so — but earn that conclusion by actually looking.

## How to Conduct the Review

Start by understanding intent. Read the task description, design doc, or PR description before looking at code so you know what the change is supposed to do.

Then read the diff and the surrounding context together. A function that looks fine in isolation can still break invariants when you see how nearby code uses it.

Trace the critical paths end-to-end. Follow data from input to output, include at least one happy path and one error path, and check whether tests cover what actually matters instead of fragile implementation details.

When the same issue appears in multiple places, report it as one finding about the underlying pattern rather than duplicating it per function.

## Your Report

Start with a brief overall assessment — what's the big picture? Then walk through your findings, grouped by severity or by theme, whichever tells a clearer story. End with your verdict: approve, approve with notes, or request changes. If you're requesting changes, be clear about which findings are blocking and which are just worth addressing.

## Resources

Check `resources/` for detailed review guidance on specific areas:

- [`resources/security.md`](resources/security.md) — trust boundaries, input validation, auth, secrets
- [`resources/concurrency.md`](resources/concurrency.md) — races, deadlocks, shared state, cancellation
- [`resources/architecture.md`](resources/architecture.md) — SOLID, abstractions, module boundaries, design alignment

Read the relevant resource when the code touches that area. You don't need all of them on every review.

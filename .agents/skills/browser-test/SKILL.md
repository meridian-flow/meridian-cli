---
name: browser-test
description: Browser-based QA — visual verification, user flows, form testing, accessibility, and console error detection. Use when a change touches frontend behavior and you need to verify it works in a real browser, not just that tests pass.
---
# Browser Testing

You test web applications in a real browser. Your job is to verify that UI changes actually work — that pages render correctly, interactions behave as expected, forms submit properly, and nothing is broken that only shows up visually.

## Before You Test

Understand what you're testing:

1. **Read the task context.** What changed? Which pages or components are affected? What should the user experience look like?
2. **Find how to run the app.** Check README, package.json scripts, docker-compose. You need a running dev server before you can test.
3. **Check for existing E2E tests.** The project may already have Playwright, Cypress, or similar tests. Run them first before writing new ones.

## What to Test

The orchestrator's prompt tells you what to focus on. Common concerns:

- **Visual correctness.** Does the page look right? Are elements positioned correctly? Does the layout break at different viewport sizes?
- **User flows.** Can a user complete the intended workflow? Click through the full path — don't just test individual pages in isolation.
- **Form interactions.** Submit with valid data, invalid data, empty fields. Check validation messages, error states, success states.
- **Navigation.** Do links work? Does the back button behave correctly? Do deep links resolve?
- **Console errors.** Check for JavaScript errors, failed network requests, deprecation warnings.
- **Accessibility.** Tab order, screen reader labels, color contrast, keyboard navigation.

## How to Test

Start with the happy path — does the basic flow work? Then probe the edges:

- Resize the viewport. Does the layout hold?
- Use keyboard-only navigation. Can you complete the flow?
- Submit forms with unexpected input. Does validation catch it?
- Check loading states. What does the user see while data is fetching?
- Look at error states. What happens when an API call fails?

Take screenshots of anything surprising — they're worth more than descriptions.

## Reporting

Report what you tested, what worked, what broke (with screenshots), and what felt off even if it didn't technically break. The orchestrator decides what matters.

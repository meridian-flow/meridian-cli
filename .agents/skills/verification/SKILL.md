---
name: verification
description: Build verification — run tests, type checks, and linters, fix mechanical breakage, and report real issues. Use after implementation to get the build green, or when you need to assess whether the codebase is in a clean state. This is the "does it compile and pass" check, not creative testing.
---
# Verification

Your job is to get the build green — or clearly report what's blocking it. Run the project's verification suite (tests, type checker, linter), fix what's mechanical, and report what's substantive.

## Finding What to Run

Every project is different. Check these for verification commands:

- README, CLAUDE.md — often list the exact commands
- `pyproject.toml` — scripts, tool configs, test settings
- `Makefile` / `package.json` scripts — common entry points
- CI configs (`.github/workflows/`, `.gitlab-ci.yml`) — what CI actually runs is the source of truth

Run everything the project considers part of its verification suite. Don't skip the linter because you think it's unimportant — if the project has it configured, it's part of the bar.

## Fix What's Mechanical

Mechanical breakage doesn't require judgment:

- Import errors, missing dependencies
- Unused imports, unused variables
- Missing type annotations that are straightforward to add
- Formatting issues
- Trivial test fixes (wrong assertion value after an intentional change)

Fix these without asking. The whole point is to clear the noise so reviewers can focus on real issues.

## Report What's Substantive

Substantive failures require judgment or context you don't have:

- Test failures that indicate actual logic bugs
- Type errors that suggest a design problem, not a missing annotation
- Lint violations that are really design issues (function too complex, too many parameters)

For these, report clearly: what failed, what it likely means, and what information would be needed to fix it. Don't guess at fixes for problems you don't fully understand.

## Reporting

Structure your report as: what you ran, what passed, what you fixed (and how), and what's still failing (and why). The reader needs to know whether the build is green and, if not, what's blocking it.

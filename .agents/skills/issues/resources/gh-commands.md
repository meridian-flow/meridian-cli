# gh CLI Reference for Issue Tracking

Detailed `gh` CLI usage for the issues skill. SKILL.md covers the when and why — this file covers the how.

## Availability Check

Run both checks before any issue operation. If either fails, skip silently.

```bash
# Check authentication
gh auth status 2>/dev/null
# Exit code 0 = authenticated

# Check repo is GitHub-hosted
gh repo view --json name 2>/dev/null
# Exit code 0 = valid GitHub repo
```

Wrap in a helper pattern:

```bash
if gh auth status 2>/dev/null && gh repo view --json name 2>/dev/null; then
  # gh is available — create the issue
else
  # gh unavailable — log locally only, no error
fi
```

## Label Taxonomy

### Category Labels

| Label | Color (hex) | Description |
|-------|-------------|-------------|
| `bug` | `d73a4a` | Bug found during implementation |
| `unexpected` | `e99d42` | Surprising behavior worth investigating |
| `backlog` | `0075ca` | Work needed but out of current scope |
| `deferred` | `fbca04` | Explicitly deferred from current work |
| `review-finding` | `7057ff` | From code review, not blocking |
| `decision-needed` | `d876e3` | Needs a decision before it can be worked on |

### Work Item Labels

| Label | Color (hex) | Description |
|-------|-------------|-------------|
| `work:<slug>` | `c5def5` | Links issue to its meridian work item |

Replace `<slug>` with the actual work item slug (e.g., `work:auth-refactor`).

### Label Creation

Run these once per repository to set up the label taxonomy. Idempotent — `gh label create` will error if the label exists, which is fine.

```bash
gh label create "bug" --color "d73a4a" --description "Bug found during implementation" 2>/dev/null
gh label create "unexpected" --color "e99d42" --description "Surprising behavior worth investigating" 2>/dev/null
gh label create "backlog" --color "0075ca" --description "Work needed but out of current scope" 2>/dev/null
gh label create "deferred" --color "fbca04" --description "Explicitly deferred from current work" 2>/dev/null
gh label create "review-finding" --color "7057ff" --description "From code review, not blocking" 2>/dev/null
gh label create "decision-needed" --color "d876e3" --description "Needs a decision before it can be worked on" 2>/dev/null
gh label create "tech-debt" --color "D4C5F9" --description "Technical debt to address later" 2>/dev/null
gh label create "enhancement" --color "A2EEEF" --description "New feature or improvement to existing functionality" 2>/dev/null
gh label create "design" --color "F9D0C4" --description "Needs design discussion or decision" 2>/dev/null
gh label create "blocked" --color "B60205" --description "Cannot proceed without external resolution" 2>/dev/null
gh label create "good-first-task" --color "7057FF" --description "Good for a new agent or contributor" 2>/dev/null
```

Create work item labels as needed:

```bash
gh label create "work:auth-refactor" --color "c5def5" --description "Meridian work item: auth-refactor" 2>/dev/null
```

## Issue Body Template

Use this structure for all issues. It gives enough context for someone to pick up the issue without needing to ask questions.

```markdown
## Context
Found during: [work item name], [phase or step]
Found by: [agent role] ([spawn ID])

## Description
[What was found — clear, specific, one to three paragraphs]

## Evidence
[File paths, code snippets, log output, reproduction steps — whatever makes it concrete]

## Suggested Action
[What should be done, or "needs investigation" if the right fix isn't clear]

---
*Created by meridian agent during `work:<slug>` implementation*
```

### Filling in the template

- **Context**: Use the active work item name and current phase. The spawn ID helps trace back to the agent session that found it.
- **Description**: State what's wrong or surprising. Be specific — "token refresh fails" is less useful than "token refresh catches all exceptions and returns None, masking network errors."
- **Evidence**: Include file paths with line numbers. Short code snippets are fine inline. For longer evidence, describe what to look for and where.
- **Suggested Action**: If you know the fix, describe it. If not, say "needs investigation" and note what you've already ruled out.

## Creating Issues

### Standard issue with labels

```bash
gh issue create \
  --title "Bug: token refresh silently swallows errors" \
  --label "bug,work:auth-refactor" \
  --body "$(cat <<'EOF'
## Context
Found during: auth-refactor, step 3 (token validation)
Found by: implementer (p107)

## Description
Token refresh catches all exceptions and returns None.

## Evidence
- `src/auth/refresh.py:45-52`

## Suggested Action
Add specific exception handling.

---
*Created by meridian agent during `work:auth-refactor` implementation*
EOF
)"
```

### Title conventions

Prefix the title with the category for scannability:

- `Bug: <what's broken>`
- `Unexpected: <what's surprising>`
- `Backlog: <what needs doing>`
- `Deferred: <what was postponed>`
- `Review: <what was found>`
- `Decision: <what needs deciding>`

### Multiple labels

Comma-separate labels in a single `--label` flag:

```bash
--label "bug,work:auth-refactor"
--label "review-finding,deferred,work:auth-refactor"
```

## Querying Issues

```bash
# All issues for a work item
gh issue list --label "work:auth-refactor"

# All bugs
gh issue list --label "bug"

# All deferred items
gh issue list --label "deferred"

# All items needing decisions
gh issue list --label "decision-needed"

# Combine filters (intersection)
gh issue list --label "bug,work:auth-refactor"

# Search by keyword
gh issue list --search "token refresh"

# View a specific issue
gh issue view 42
```

## Closing Issues

### When the fix is committed

```bash
gh issue close 42 --comment "Fixed in $(git rev-parse --short HEAD)"
```

### When a decision is made

```bash
gh issue close 42 --comment "Decided: use JWT with 15-minute expiry."
```

### Automatic closure via commit message

Include `Fixes #42` or `Closes #42` in a commit message and GitHub closes the issue automatically when the commit reaches the default branch.

## Updating Issues

### Add context to an existing issue

```bash
gh issue comment 42 --body "Additional context: this also affects the session refresh path in src/auth/session.py:112"
```

### Re-label an issue

```bash
gh issue edit 42 --add-label "deferred" --remove-label "backlog"
```

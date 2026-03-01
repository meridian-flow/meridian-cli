# Default Model Guidance

Use this default only when no custom files exist in `references/model-guidance/*.md`.

## Baseline picks

- Implementation: `gpt-5.3-codex`
- Review (medium/high risk): fan out across model families
- Fast/iterative UI loops: `claude-sonnet-4-6`
- Nuanced correctness/architecture: `claude-opus-4-6`
- Lightweight commit/message tasks: `claude-haiku-4-5`

## Practical rules

1. Prefer the smallest model choice that controls risk.
2. Use multiple reviewers only when risk justifies it.
3. Keep skill sets minimal and task-relevant.

# Contributing

Thanks for contributing to `meridian-channel`.

## Getting Started

The quickest path for local development is:

```bash
uv sync --extra dev
```

For the full install and test workflow, see [docs/development-install.md](docs/development-install.md).

## Running Tests

Use the standard repo checks before sending changes:

```bash
uv run pytest-llm
uv run pyright
```

When you are iterating on a narrow area, targeted `uv run pytest ...` commands
are fine, but the full checks above are the baseline.

## Code Style

- Format and lint with `ruff`.
- Keep type checking clean under `pyright` strict mode.
- Reuse existing state-layer and CLI patterns instead of introducing parallel abstractions.
- Prefer explicit file-authoritative behavior over hidden state or implicit context.

## Commit Guidelines

- Keep commits small and atomic.
- Write descriptive commit messages that explain the behavior change.
- Run the relevant verification before committing.
- If a change updates user-facing behavior, update the docs in the same commit.

## Terminology

Use `spawn` for user-facing and domain language, not `run`.

Examples:
- say `meridian spawn`
- say `spawn id`
- avoid introducing new public `run` nouns in docs, commands, or errors

See [docs/developer-terminology.md](docs/developer-terminology.md) for the
canonical terminology rules.

## Submitting Changes

- Open a focused PR or patch series.
- Include tests when behavior changes.
- Call out any command-surface, state-format, or docs changes clearly.
- Link related issues or plans when they exist.

## Reporting Issues

Report bugs, regressions, and documentation issues in
[GitHub Issues](https://github.com/haowjy/meridian-channel/issues).

Useful issue reports include:
- the command you ran
- the exact error output
- your harness and model
- any relevant repo or space context

## Code of Conduct

By participating in this project, you agree to follow the
[Code of Conduct](CODE_OF_CONDUCT.md).

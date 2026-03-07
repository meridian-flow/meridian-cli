# Development Install and Test

This page is the developer workflow for installing `meridian-channel` from source and testing changes.

## Prerequisites

- Python 3.12+
- `uv` installed
- One harness CLI available for end-to-end checks (Claude CLI, Codex CLI, or OpenCode)

```bash
git clone https://github.com/haowjy/meridian-channel.git
cd meridian-channel
```

## 1) Install Developer Dependencies

```bash
uv sync --extra dev
```

This creates/updates the local virtual environment with test and type-check tooling.

## 2) Install the CLI Under Test

Use one of these modes depending on what you are validating.

Editable local install (best default for active coding):

```bash
uv tool install --force --editable . --no-cache
```

Local snapshot install (non-editable, deployed-like behavior from current checkout):

```bash
uv tool install --force . --no-cache
```

Wheel install (closest to published artifact behavior):

```bash
uv build
uv tool install --force dist/*.whl
```

## 3) Verify the Install

```bash
meridian --version
which meridian
uv tool list
```

## 4) Run Developer Test Commands

Project-standard checks:

```bash
uv run pytest-llm
uv run pyright
```

Useful targeted test patterns during development:

```bash
uv run pytest tests/config -q
uv run pytest tests/space tests/test_space -q
uv run pytest tests/harness tests/prompt tests/exec -q
uv run pytest tests/ops tests/test_state -q
```

## 5) Validate CLI Behavior in the Repo Context

```bash
uv run meridian --help
uv run meridian doctor
```

Use `uv run meridian ...` when you want commands guaranteed to run against the repo's synced environment.

## If `meridian` Is Not on PATH

Find the tool bin directory:

```bash
uv tool dir --bin
```

Recommended:

```bash
uv tool update-shell
```

Then restart your shell, or source your shell rc file.

Manual fallback (bash):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Manual fallback (zsh):

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Manual fallback (fish):

```fish
fish_add_path $HOME/.local/bin
```

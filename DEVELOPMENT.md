# Development

## Setup

```bash
git clone https://github.com/haowjy/meridian-channel.git
cd meridian-channel
uv sync --extra dev
```

## Verify

```bash
uv run meridian --version
uv run meridian doctor
```

## Install Validation

Use these when you want to verify the installed CLI behavior, not just `uv run`
from the checkout.

Editable install:

```bash
uv tool install --force --editable . --no-cache
```

Snapshot install from the current checkout:

```bash
uv tool install --force . --no-cache
```

Then verify the installed tool:

```bash
meridian --version
uv tool list
```

## Test

```bash
uv run pytest-llm
uv run pyright
```

## Release

Use the release helper to bump the package version, create a release commit,
and create the matching `v<version>` tag in one step:

The package version currently lives in `src/meridian/__init__.py` as
`__version__`.

```bash
scripts/release.sh patch
scripts/release.sh 0.1.0 --push
```

By default it updates `src/meridian/__init__.py`, commits the change, and
creates an annotated tag locally. Pass `--push` to push both the current branch
and the new tag.

## Run from source

```bash
uv run meridian --help
```

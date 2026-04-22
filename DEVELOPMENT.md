# Development

## Setup

```bash
git clone https://github.com/meridian-flow/meridian-cli.git
cd meridian-cli
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

Snapshot install from the current checkout:

```bash
uv tool install --force . --no-cache --reinstall
```

Editable install:

```bash
uv tool install --force --editable . --no-cache --reinstall
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

## App Server + Frontend

The app is a FastAPI backend serving a Vite/React frontend.

### Backend only

```bash
uv run meridian app --port 7676
# Serves API at http://localhost:7676
# Also serves frontend/dist/ at / if built
```

### Frontend dev (hot reload)

```bash
# Terminal 1: backend
uv run meridian app --port 7676

# Terminal 2: Vite dev server
cd frontend && pnpm dev
# http://localhost:5173 — proxies /api and /ws to :7676
```

For remote access (working from a remote machine):

```bash
cd frontend && pnpm dev --host 0.0.0.0
# http://<remote-ip>:5173
```

### Production build

```bash
cd frontend && pnpm build   # builds to frontend/dist/
uv run meridian app --port 7676
# Frontend served at http://localhost:7676
```

### Storybook (component playground)

```bash
cd frontend && pnpm storybook
# http://localhost:6006 (already binds 0.0.0.0 for remote access)
```

### Frontend setup (first time)

```bash
cd frontend && pnpm install
```

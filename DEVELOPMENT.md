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

The app is a FastAPI backend serving a Vite/React frontend. Local dev uses
[portless](https://github.com/vercel-labs/portless) for stable, worktree-aware
URLs — no port juggling, and multiple worktrees run the full stack simultaneously.

### Prerequisites

```bash
npm install -g portless        # one-time
portless trust                 # trust the local CA (one-time)
cd frontend && pnpm install    # frontend deps (first time)
```

### Dev workflow

```bash
# Terminal 1: backend
make backend
# → https://api.meridian.localhost

# Terminal 2: frontend
make frontend
# → https://app.meridian.localhost (proxies /api and /ws to backend)
```

In a git worktree (e.g. `feature/new-ui`), URLs auto-prefix automatically:
`https://new-ui.app.meridian.localhost`, `https://new-ui.api.meridian.localhost`.

### Share over Tailscale

```bash
make backend-share
make frontend-share
```

### Backend only (no portless)

```bash
uv run meridian chat --port 7676
# → http://localhost:7676
```

### Production build

```bash
make build
uv run meridian app --port 7676
# Frontend served at http://localhost:7676
```

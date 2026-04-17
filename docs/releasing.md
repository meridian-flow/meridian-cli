# Releasing

Use the repo release helper:

```bash
scripts/release.sh patch
scripts/release.sh 0.2.0
```

Default to `patch`, especially while Meridian is still in `0.0.x`.
Omit `minor` and `major` in normal release flow. Use an explicit version only when the user asks for a larger version jump.

What the script does:

- runs pre-release checks: `uv run ruff check .`, `uv run pyright`, `uv run python -m pytest -x -q`
- bumps `src/meridian/__init__.py`
- creates release commit `Release X.Y.Z`
- creates annotated tag `vX.Y.Z`
- optionally pushes with `--push --remote <name>`

Recommended flow:

1. Update `CHANGELOG.md`: move the release notes out of `[Unreleased]` into `## [X.Y.Z] - YYYY-MM-DD`, then open a fresh empty `[Unreleased]` above it.
2. Stage the exact release content you want included before running the script. The script explicitly adds the version file, then commits the current index.
3. Run `scripts/release.sh patch` for normal releases.
4. Verify the result with `git show --stat HEAD` and `git rev-parse --verify vX.Y.Z`.

Example:

```bash
git add CHANGELOG.md path/to/release-fix.py path/to/release-test.py
scripts/release.sh patch
```

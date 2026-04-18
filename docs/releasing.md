# Releasing

Use the repo release helper:

```bash
scripts/release.sh patch          # 0.0.33 → 0.0.34 (default choice)
scripts/release.sh rc             # 0.0.33 → 0.0.34-rc.1 (release candidate)
scripts/release.sh 0.2.0          # explicit version
```

Default to `patch`, especially while Meridian is still in `0.0.x`.
Omit `minor` and `major` in normal release flow. Use an explicit version only when the user asks for a larger version jump.

## Release Candidates

Use `rc` when you want to test a release before cutting the final version:

```bash
scripts/release.sh rc             # 0.0.33 → 0.0.34-rc.1
scripts/release.sh rc             # 0.0.34-rc.1 → 0.0.34-rc.2
scripts/release.sh 0.0.34         # graduate RC to final release
```

RCs are tagged and can be published to PyPI for testing. The commit message says "Release candidate X.Y.Z-rc.N" to distinguish from final releases.

## What the Script Does

- Runs pre-release checks: `uv run ruff check .`, `uv run pyright`, `uv run python -m pytest -x -q`
- Bumps `src/meridian/__init__.py`
- Creates release commit `Release X.Y.Z` (or `Release candidate X.Y.Z-rc.N`)
- Creates annotated tag `vX.Y.Z` (or `vX.Y.Z-rc.N`)
- Optionally pushes with `--push --remote <name>`

## Recommended Flow

1. Update `CHANGELOG.md`: move the release notes out of `[Unreleased]` into `## [X.Y.Z] - YYYY-MM-DD`, then open a fresh empty `[Unreleased]` above it.
2. Stage the exact release content you want included before running the script. The script explicitly adds the version file, then commits the current index.
3. Run `scripts/release.sh patch` for normal releases, or `scripts/release.sh rc` for release candidates.
4. Verify the result with `git show --stat HEAD` and `git rev-parse --verify vX.Y.Z`.

Example:

```bash
git add CHANGELOG.md path/to/release-fix.py path/to/release-test.py
scripts/release.sh patch
```

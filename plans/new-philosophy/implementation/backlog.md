# Spawn Migration Backlog

## 2026-03-02

- Pre-existing dirty worktree includes docs that are partially migrated to `spawn` while code is still largely `run`-named.
- `_docs/cli-spec-agent.md` and `_docs/cli-spec-human.md` already exist before this execution; will verify against plan rather than recreating blindly.
- `doctor` orphan-repair behavior is intentionally skipped when `MERIDIAN_SPACE_ID` is set; this changed expected test behavior under autouse env fixtures.
- Mechanical `run`→`spawn` replacement also touched non-domain uses (`uv run`, `subprocess.run`); these had to be restored manually in tests.
- `uv run pyright` currently reports many strict-type diagnostics unrelated to this migration slice; full pytest suite is green.

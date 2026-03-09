# Testing With Codex

Use this reference when you are running Meridian smoke tests from a Codex session rather than from a normal terminal.

## Sandbox and `uv`

`uv run meridian ...` may fail before Meridian starts if `uv` tries to use a cache directory outside the allowed sandbox roots. If that happens, set a cache path inside an allowed location:

```bash
export UV_CACHE_DIR=/tmp/uv-cache
mkdir -p "$UV_CACHE_DIR"
```

This isolates `uv` cache behavior from Meridian behavior.

## Scratch-Repo Checklist

For scratch-repo tests, usually set all three:

```bash
export MERIDIAN_REPO_ROOT=/tmp/test-repo
export MERIDIAN_STATE_ROOT=/tmp/test-repo/.meridian
export UV_CACHE_DIR=/tmp/uv-cache
```

This prevents state leakage into the real repo and keeps `uv` cache access predictable.

## Sync-Specific Advice

When validating `meridian sync` from Codex:

- Run the local-path round trip in [`tests/smoke/sync/install-cycle.md`](/home/jimyao/gitrepos/meridian-channel/tests/smoke/sync/install-cycle.md)
- If remote resolution, lock semantics, or `.claude/` materialization changed, also run one real GitHub-source install
- Inspect `.agents/`, `.claude/`, `.meridian/config.toml`, and `.meridian/sync.lock`, not just command output

The focused smoke doc (`tests/smoke/sync/install-cycle.md`) contains the concrete remote example and should remain the source of truth for exact commands.

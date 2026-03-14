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

## Permission Tiers and Sandbox Nesting

Meridian maps agent-profile `sandbox:` values to harness-specific sandbox options. The three tiers are:

| Tier             | Codex flag                               | Network | File writes        |
|------------------|------------------------------------------|---------|--------------------|
| `read-only`      | `--sandbox read-only`                    | ❌      | ❌                 |
| `workspace-write` | `--sandbox workspace-write`             | ❌      | ✅ (workspace only)|
| `full-access`    | `--dangerously-bypass-approvals-and-sandbox` | ✅  | ✅ (everywhere)    |

### The Sandbox Nesting Trap

Codex's `workspace-write` sandbox uses Linux Landlock to restrict network access at the OS level. **Child processes inherit these restrictions.** This means:

- A spawn running under `workspace-write` **cannot launch nested spawns** that need API access (e.g., `meridian spawn` inside a codex spawn). The child's API calls fail with `EPERM` on the websocket connection.
- This applies to ALL child process network access, not just meridian — `curl`, `pip install`, `npm install`, etc. will also fail.
- The restriction is inherited at the kernel level and cannot be bypassed by the child process.

### Testing Permission Tiers

When smoke-testing spawn lifecycle, test profile sandbox values explicitly:

```bash
# Dry-run to verify sandbox mapping from an agent profile
uv run meridian --json spawn --dry-run -p "test" --agent reviewer
# reviewer profile should set sandbox: read-only/workspace-write/full-access as needed

# Verify the generated command includes the expected sandbox flags
```

For actual spawn execution tests that need network (most real spawns do), use an agent with `sandbox: full-access` and optionally `--yolo` to bypass interactive approvals:

```bash
uv run meridian spawn -p "echo hello" --agent coder --yolo --foreground
```

### When to Use Each Tier

- **`read-only`**: Safe for analysis-only tasks (code review, search, read files). No network, no writes.
- **`workspace-write`**: Good for implementation tasks that don't need network. Blocks API calls from child processes.
- **`full-access`**: Required when spawns need to make API calls, install packages, or launch nested spawns. Use this as the default for smoke testing unless specifically testing sandbox behavior.

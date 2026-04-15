# Fix env propagation: MERIDIAN_WORK_DIR derivation + CLAUDE_AUTOCOMPACT unblock

Two small, related fixes to meridian's child-env propagation layer. Both live in `src/meridian/lib/launch/env.py` and `src/meridian/lib/launch/constants.py`. The changes should land in one commit.

Context: https://github.com/meridian-flow/meridian-cli/issues/12 captures the full regression analysis and architectural reasoning. Read it before starting if anything below is ambiguous.

## Fix 1: Add MERIDIAN_WORK_DIR derivation fallback to `_normalize_meridian_env`

**Current state:** `_normalize_meridian_env` in `src/meridian/lib/launch/env.py` has a three-level fallback for `MERIDIAN_FS_DIR` — explicit env > derived from `MERIDIAN_STATE_ROOT` > derived from `MERIDIAN_REPO_ROOT`. It runs inside `inherit_child_env` at the tail of every harness child env assembly. There is no equivalent fallback for `MERIDIAN_WORK_DIR`.

**The regression:** commit `81e0d6b` (streaming-parity-fixes phase 6 — "shared launch context and env invariants") consolidated subprocess and streaming launch context through `launch/context.py:RuntimeContext`, which only reads `MERIDIAN_WORK_DIR` from the parent env (`os.getenv`). It never consults meridian state. And `meridian work switch X` updates `.meridian/sessions.jsonl` but does not mutate the running parent session's env. So if the topmost launch started before a work item was active, or via a code path that didn't inject `WORK_DIR` into `plan_overrides`, the var never enters the spawn tree — every child sees an empty value and silently expands `$MERIDIAN_WORK_DIR/...` to `/...`.

**The fix:** extend `_normalize_meridian_env` in `src/meridian/lib/launch/env.py` with a `MERIDIAN_WORK_DIR` derivation branch that mirrors the `MERIDIAN_FS_DIR` pattern. When the var is missing from the child env, derive it by looking up the active work item from meridian state and resolving the scratch dir path.

The derivation helpers already exist:
- `meridian.lib.state.session_store.get_session_active_work_id(state_root: Path, chat_id: str) -> str | None`
- `meridian.lib.state.paths.resolve_work_scratch_dir(state_root: Path, work_id: str) -> Path`

Pseudocode shape for the new branch inside `_normalize_meridian_env`:

```python
# After the FS_DIR branch returns or the function falls through, add:
explicit_work = env.get("MERIDIAN_WORK_DIR", "").strip()
if explicit_work:
    env["MERIDIAN_WORK_DIR"] = explicit_work
    return  # or continue depending on how you structure the function

state_root_raw = env.get("MERIDIAN_STATE_ROOT", "").strip()
chat_id = env.get("MERIDIAN_CHAT_ID", "").strip()
if state_root_raw and chat_id:
    state_root = Path(state_root_raw).expanduser()
    active_work_id = get_session_active_work_id(state_root, chat_id)
    if active_work_id:
        env["MERIDIAN_WORK_DIR"] = resolve_work_scratch_dir(state_root, active_work_id).as_posix()
```

You will need to restructure `_normalize_meridian_env` to handle two vars instead of one and to avoid the early `return` pattern that skips WORK_DIR processing when FS_DIR is set. Rename/split the function if that makes it cleaner — preserve the existing FS_DIR derivation behavior byte-for-byte.

Handle the failure cases gracefully. If `state_root` or `chat_id` is missing from the env, skip the derivation silently — the child's env just won't have WORK_DIR, same as today. If `get_session_active_work_id` returns `None`, skip. If anything raises unexpectedly, don't crash the launch — let the child run without WORK_DIR and let the downstream skill-using agent fail with a clear error instead.

**Deeper cleanup deferred to a separate issue:** `core/context.py` has a second `RuntimeContext` class that produces its own env overrides on a code path that is no longer active after phase 6. Do not touch `core/context.py` in this commit. The regression fix stays scoped to `launch/env.py` and `launch/constants.py`.

## Fix 2: Unblock CLAUDE_AUTOCOMPACT_PCT_OVERRIDE from child env inheritance

**Current state:** `BLOCKED_CHILD_ENV_VARS` in `src/meridian/lib/launch/constants.py` contains exactly one entry — `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`. This var is stripped from any inherited child env, which means the user's explicit setting in the parent env never flows through to spawned children, even when meridian has no opinion about autocompact for that spawn.

**Why it's wrong:** meridian already layers its own autocompact override on top of inherited env via `env_overrides` (see `launch/command.py:49` and `ops/spawn/execute.py:146`). When meridian's profile/CLI sets autocompact, meridian's value wins naturally via override precedence — the blocklist adds nothing to the "meridian has an opinion" case. The blocklist only affects the "meridian is silent" case, where it silently drops the user's explicit env setting instead of letting it flow through.

**The precedence we want:**
1. Meridian profile/CLI sets autocompact → meridian's override wins
2. Meridian is silent, user set `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` in parent env → user's setting flows through
3. Meridian is silent, user didn't set it → child runs with Claude default

Current behavior collapses cases 2 and 3. We want them separated.

**The fix:** remove `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` from `BLOCKED_CHILD_ENV_VARS` in `src/meridian/lib/launch/constants.py`. The resulting set will be empty — you can either keep it as `frozenset()` (preferred, preserves the blocklist mechanism for future use) or you can simplify the `inherit_child_env` signature to drop the blocked parameter entirely. Prefer the lighter-touch option: keep the mechanism, empty the default set.

**Verify no regressions in the meridian-overrides-win case:** the test `test_inherit_child_env_keeps_parent_env_and_drops_autocompact_override` in `tests/exec/test_permissions.py` specifically asserts the drop behavior. That assertion is now wrong — rewrite it to match the new semantics (parent env value flows through when no override is set, meridian override wins when one is). Add a new test that verifies the meridian-override-wins case explicitly.

The per-adapter blocklist in `src/meridian/lib/harness/connections/claude_ws.py` extends `BLOCKED_CHILD_ENV_VARS` with its own additions — check that the claude_ws path still behaves correctly after the base set empties out. If `claude_ws` still needs to block `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` for its own reasons, it can add it locally. Don't cargo-cult the block into claude_ws if the base removal is sufficient.

## Regression tests

Add tests to cover both fixes. For the WORK_DIR derivation, the key scenario is "parent env has no WORK_DIR but state has an active work item for the chat_id; child env receives the resolved path." For the autocompact unblock, cover the three precedence cases above.

Place tests alongside the existing coverage in `tests/exec/test_permissions.py` if that module is the right home for env-propagation behavior. If not, pick the nearest existing module for env tests.

## Non-goals

- Do not merge `core/context.py` and `launch/context.py`. Separate cleanup.
- Do not delete `sanitize_child_env` (the dead code). Separate cleanup.
- Do not change the `launch/context.py:RuntimeContext` allowlist. The fix is in `_normalize_meridian_env`, which runs later in the pipeline, so the allowlist isn't involved.
- Do not touch the `sanitize_child_env` tests.

## Lint and type gates

- `uv run ruff check .` — must pass.
- `uv run pyright` — must stay at 0 errors.
- `uv run pytest-llm tests/exec/test_permissions.py` at minimum, plus any new test file you add.

Use `uv` for all Python tooling per the project's CLAUDE.md conventions.

## Deliverables

- Modified `src/meridian/lib/launch/env.py` (new WORK_DIR branch)
- Modified `src/meridian/lib/launch/constants.py` (empty blocklist)
- Modified `tests/exec/test_permissions.py` (updated autocompact assertion + new tests)
- Any new test file you create for the WORK_DIR derivation
- All lint and type gates green
- One commit with a descriptive message explaining both fixes and referencing issue #12

Report back with the commit SHA, changed file list, and test output when done.

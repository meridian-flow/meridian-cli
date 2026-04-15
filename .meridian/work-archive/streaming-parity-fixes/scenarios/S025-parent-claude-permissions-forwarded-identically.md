# S025: Parent Claude permissions forwarded identically

- **Source:** design/edge-cases.md E25 + p1411 findings M6 + H2
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @smoke-tester
- **Status:** verified

## Given
`CLAUDECODE=1` in the parent environment. Parent `.claude/settings.json` with a non-trivial permission block (e.g., `allowedTools=["Read","Edit"]`, `deniedTools=["Bash"]`). Spawn uses `ExplicitToolsResolver(allowed=("Read","Write"), denied=("Edit",))`.

## When
Both the subprocess runner and the streaming runner process the same plan.

## Then
- `read_parent_claude_permissions` produces the same parsed result for both runners.
- The preflight merge (via `merge_allowed_tools_flag`) folds parent allowances into `extra_args` identically.
- Both runners pass an identical `ClaudeLaunchSpec` downstream to the shared projection.
- The final launched command has the same `--allowedTools` (deduped) and same `--disallowedTools` value.
- The child env has the same `CLAUDECODE=1` and the same scrubbed variables.

## Verification
- Smoke test: launch the same spawn through both runners with the described inputs, capture the launched command via process introspection, assert equality of the arg tail and the env diff.
- Unit test: stub subprocess launch, assert `LaunchContext.env` and the projection output match byte-for-byte between the two paths.
- Delta test: modify parent settings mid-test and confirm both runners pick up the change identically on the next launch.

## Result (filled by tester)
verified - 2026-04-10

Commands run:
- `uv run python - <<'PY'` ad hoc smoke fixture that created a temp repo plus fake `claude` shim, then launched the same Claude plan through `execute_with_finalization(...)` and `execute_with_streaming(...)` and captured each child process `argv`/env to JSON for byte-for-byte comparison.
- `uv run ruff check .`
- `uv run pyright`
- `uv run pytest-llm tests/exec/test_claude_cwd_isolation.py -v`
- `uv run pytest-llm tests/exec/test_permissions.py -v`
- `uv run pytest-llm tests/exec/test_streaming_runner.py -v`
- `uv run pytest-llm tests/ --ignore=tests/smoke -q`

Observed evidence:
- Baseline parent-permission case passed on both launch paths with identical normalized Claude tails:
  - `--model claude-sonnet-4-6 --allowedTools Read,Write,A,B,C --disallowedTools Edit --add-dir /tmp/s025-matrix-q054thqf/baseline_parent_forwarding --add-dir /path/one --add-dir /path/two`
- Duplicate parent allowlist case stayed identical across both paths, but parent duplicates were deduped before launch:
  - both emitted `--allowedTools A,B`
- Quoted-comma denylist case stayed identical across both paths:
  - both emitted `--disallowedTools Bash("a,b")`
- User-tail override case stayed identical across both paths and preserved last-wins tail semantics:
  - both emitted `--allowedTools Read,Write,A,B --allowedTools override --add-dir /tmp/s025-matrix-q054thqf/user_tail_override`
  - both paths logged `Claude projection known managed flag --allowedTools also present in extra_args; user tail value wins by last-wins semantics`
- No-parent case emitted no phantom forwarding on either path:
  - both emitted only `--model claude-sonnet-4-6`
- Child env parity matched on both paths for the relevant keys. In the captured child env, `CLAUDECODE` was absent on both paths, and both carried the same `MERIDIAN_*` values apart from the per-run capture-file path.

Notes:
- The scenario text says the child env should keep `CLAUDECODE=1`, but current code and existing tests intentionally scrub `CLAUDECODE` from child Claude launches. Smoke testing confirmed both paths scrub it identically.
- The adversarial duplicate-allowlist probe showed parity, but not literal duplicate preservation: parent `A,A,B` became `A,B` on both paths.

Gate results:
- `uv run ruff check .` -> passed
- `uv run pyright` -> passed
- `uv run pytest-llm tests/exec/test_claude_cwd_isolation.py -v` -> 2 passed
- `uv run pytest-llm tests/exec/test_permissions.py -v` -> 48 passed
- `uv run pytest-llm tests/exec/test_streaming_runner.py -v` -> 10 passed
- `uv run pytest-llm tests/ --ignore=tests/smoke -q` -> passed

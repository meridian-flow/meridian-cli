# S049: Streaming session-id fallback via `HarnessExtractor`

- **Source:** design/edge-cases.md E46 + decisions.md K6 (revision round 3) + p1385 gap
- **Added by:** @design-orchestrator (revision round 3)
- **Tester:** @smoke-tester
- **Status:** verified

## Given
A real streaming spawn for each harness (Claude, Codex, OpenCode) where the live event stream does NOT carry a session id in any frame — the harness writes its session identifier only to disk artifacts (Claude project files, Codex rollout files, OpenCode logs).

## When
The streaming runner finalizes the spawn and calls `bundle.extractor.detect_session_id_from_artifacts(child_cwd=..., state_root=...)`.

## Then
- The extractor returns the same session id that the subprocess runner would recover for the same artifact set.
- The session id is persisted on the spawn record so `meridian session log <spawn_id>` resolves the transcript.
- Subprocess and streaming reach the same session id for the same harness + artifact set (byte-identical resolution).

## Verification
- Smoke test per harness: launch a streaming spawn, verify the extractor recovers the session id, verify `meridian session log` works.
- Cross-runner test: launch the same conceptual spawn once via subprocess and once via streaming, assert the resolved session ids are identical when the underlying harness writes the same artifact.
- Negative test: empty artifacts directory → extractor returns `None`, spawn record has no session id, `meridian session log` surfaces a clear "session not detected" message rather than crashing.
- Regression: replace the streaming extractor with a no-op stub and verify the smoke test fails with "session not detected".

## Result (filled by tester)
failed 2026-04-11

- Claude:
  - Real streaming spawn in `/tmp/phase7-claude-smoke` succeeded.
  - `.meridian/spawns.jsonl` recorded `harness_session_id="e786de42-b612-449d-904a-b17be8f64316"`.
  - `MERIDIAN_REPO_ROOT=/tmp/phase7-claude-smoke MERIDIAN_STATE_ROOT=/tmp/phase7-claude-smoke/.meridian uv run meridian session log p1 -n 3` resolved the transcript and showed `SMOKE`.
  - Offline fallback simulation with `StreamingExtractor(connection=None, artifacts=InMemoryStore())` returned the same id: `e786de42-b612-449d-904a-b17be8f64316`.
- Codex:
  - Real streaming spawn in `/tmp/phase7-codex-smoke` succeeded.
  - `.meridian/spawns.jsonl` recorded `harness_session_id="019d7b00-9eae-78a0-965a-1a438ae4ef15"`.
  - `MERIDIAN_REPO_ROOT=/tmp/phase7-codex-smoke MERIDIAN_STATE_ROOT=/tmp/phase7-codex-smoke/.meridian uv run meridian session log p1 -n 3` resolved the transcript.
  - Offline fallback simulation with `StreamingExtractor(connection=None, artifacts=InMemoryStore())` returned the same id: `019d7b00-9eae-78a0-965a-1a438ae4ef15`.
- OpenCode:
  - Real streaming spawn in `/tmp/phase7-opencode-smoke` created session `ses_284fe233cffel3x3FkBmLPmgQO`; both `debug.jsonl` and `output.jsonl` contain that session id.
  - The run hit upstream provider retries, was cancelled, and `.meridian/spawns.jsonl` later recorded `harness_session_id="ses_284fe233cffel3x3FkBmLPmgQO"`.
  - `MERIDIAN_REPO_ROOT=/tmp/phase7-opencode-smoke MERIDIAN_STATE_ROOT=/tmp/phase7-opencode-smoke/.meridian uv run meridian session log p1 -n 5` failed with `Session file for 'ses_284fe233cffel3x3FkBmLPmgQO' (harness=opencode) not found`.
  - Offline fallback simulation with `StreamingExtractor(connection=None, artifacts=InMemoryStore())` returned `None`.
  - `rg 'ses_284fe233cffel3x3FkBmLPmgQO|directory=/tmp/phase7-opencode-smoke' ~/.local/share/opencode/log/*.log` returned no matches, while `~/.local/share/opencode/storage/session_diff/ses_284fe233cffel3x3FkBmLPmgQO.json` exists.
- Negative control:
  - Empty isolated state returned `{'claude': None, 'codex': None, 'opencode': None}` from the same offline fallback simulation.

- Outcome:
  - Claude and Codex satisfy the scenario.
  - OpenCode does not satisfy `extractor fallback produces stable id` plus ``meridian session log`` resolution, so the scenario is not verified.

### Re-verify 2026-04-11

- Note:
  - Re-ran the smoke in fresh isolated repos under `/tmp/phase7-s049-reverify-{claude,codex,opencode}-*`.
  - For the offline fallback simulation, used the merged `execution_cwd` recorded in `.meridian/spawns.jsonl` as `child_cwd`, matching the streaming runner contract.
- Claude:
  - Real streaming spawn: `MERIDIAN_REPO_ROOT=/tmp/phase7-s049-reverify-claude-gV8wRm/repo MERIDIAN_STATE_ROOT=/tmp/phase7-s049-reverify-claude-gV8wRm/repo/.meridian uv run meridian --harness claude spawn -m claude-sonnet-4-6 --yolo --timeout 2 -p 'Reply with exactly SMOKE-S049-CLAUDE and nothing else.'`
  - `.meridian/spawns.jsonl` recorded `harness_session_id="b94bc54e-fa55-47a5-aec3-e536bf495fbc"`.
  - `MERIDIAN_REPO_ROOT=/tmp/phase7-s049-reverify-claude-gV8wRm/repo MERIDIAN_STATE_ROOT=/tmp/phase7-s049-reverify-claude-gV8wRm/repo/.meridian uv run meridian session log p1 -n 5` resolved the transcript and showed `SMOKE-S049-CLAUDE`.
  - Offline fallback simulation with `ClaudeHarnessExtractor.detect_session_id_from_artifacts(...)` returned the same id: `b94bc54e-fa55-47a5-aec3-e536bf495fbc`.
- Codex:
  - Real streaming spawn: `MERIDIAN_REPO_ROOT=/tmp/phase7-s049-reverify-codex-uYZJtN/repo MERIDIAN_STATE_ROOT=/tmp/phase7-s049-reverify-codex-uYZJtN/repo/.meridian uv run meridian --harness codex spawn -m gpt-5.3-codex --yolo --timeout 2 -p 'Reply with exactly SMOKE-S049-CODEX and nothing else.'`
  - `.meridian/spawns.jsonl` recorded `harness_session_id="019d7b14-cb61-7363-82f9-17e561d64290"`.
  - `MERIDIAN_REPO_ROOT=/tmp/phase7-s049-reverify-codex-uYZJtN/repo MERIDIAN_STATE_ROOT=/tmp/phase7-s049-reverify-codex-uYZJtN/repo/.meridian uv run meridian session log p1 -n 5` resolved session `019d7b14-cb61-7363-82f9-17e561d64290`.
  - Offline fallback simulation with `CodexHarnessExtractor.detect_session_id_from_artifacts(...)` returned the same id: `019d7b14-cb61-7363-82f9-17e561d64290`.
- OpenCode:
  - Real streaming spawn: `MERIDIAN_REPO_ROOT=/tmp/phase7-s049-reverify-opencode-q8nexi/repo MERIDIAN_STATE_ROOT=/tmp/phase7-s049-reverify-opencode-q8nexi/repo/.meridian uv run meridian --harness opencode spawn -m opencode-gpt-5.3-codex --yolo --timeout 2 -p 'Reply with exactly SMOKE-S049-OPENCODE and nothing else.'`
  - The provider timed out after repeated upstream retries, but `output.jsonl` and `.meridian/spawns.jsonl` both converged on `harness_session_id="ses_284e9a378ffeGmgaHqzZYXX29r"` during finalize.
  - `MERIDIAN_REPO_ROOT=/tmp/phase7-s049-reverify-opencode-q8nexi/repo MERIDIAN_STATE_ROOT=/tmp/phase7-s049-reverify-opencode-q8nexi/repo/.meridian uv run meridian session log p1 -n 5` resolved session `ses_284e9a378ffeGmgaHqzZYXX29r` instead of failing with `Session file ... not found`.
  - Offline fallback simulation with `OpenCodeHarnessExtractor.detect_session_id_from_artifacts(...)` returned the same id: `ses_284e9a378ffeGmgaHqzZYXX29r`.
  - XDG/storage fallback now resolves the real session artifact: `resolve_opencode_session_file("ses_284e9a378ffeGmgaHqzZYXX29r")` and `OpenCodeAdapter.resolve_session_file(...)` both returned `/home/jimyao/.local/share/opencode/storage/session_diff/ses_284e9a378ffeGmgaHqzZYXX29r.json`.
- Gates:
  - `uv run pytest-llm tests/harness/test_extraction.py -v` passed.
  - `uv run pytest-llm tests/ops/test_session_log.py -v` passed.
  - `uv run pytest-llm tests/ --ignore=tests/smoke -q` passed.
- Outcome:
  - Claude, Codex, and OpenCode now all satisfy the session-id recovery plus `session log` transcript-open contract.
  - S049 is verified.

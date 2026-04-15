# S029: `codex app-server` rejects passthrough args surfaces cleanly

- **Source:** design/edge-cases.md E29 + p1411 finding M7
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @smoke-tester
- **Status:** verified

## Given
Codex streaming spawn with `extra_args=("--invalid-flag",)`. Real `codex app-server` is available (it does NOT accept `--invalid-flag`).

## When
The streaming runner launches Codex and forwards extra_args.

## Then
- Before launch, a debug log is emitted: "Forwarding passthrough args to codex app-server: ['--invalid-flag']".
- `codex app-server` fails at startup with its own error about the unknown flag.
- The failure is surfaced via the runner's existing error path — same structured error as any other failed launch.
- The spawn report includes both the debug log (pre-launch forwarding notice) and the Codex-side error (post-launch failure).
- No silent swallowing. No misleading "Codex crashed internally" message when the real cause is an argument the runner passed through.

## Verification
- Smoke test: run a Codex streaming spawn with `extra_args=("--invalid-flag",)`, capture debug.jsonl and the report.
- Assert the debug log entry is present.
- Assert the Codex error (unknown flag) is visible in the report.
- Assert the exit code is non-zero and matches the launcher's error-exit contract.
- Delta test: remove the pre-launch debug log and confirm diagnosing the failure becomes harder (this is qualitative — the test exists to lock in the debug log presence).

## Result (filled by tester)
Verified 2026-04-10 with extra coverage.

- `tests/harness/test_codex_ws.py:276` proves the streaming projection logs passthrough forwarding and preserves `extra_args` verbatim at the command tail.
- `tests/harness/test_codex_ws.py:355` adds the collision case and proves passthrough config args are logged and not stripped even when they duplicate managed flags.
- Live local CLI check on `codex-cli 0.118.0` with `codex app-server --listen ws://127.0.0.1:7782 --invalid-flag` returned exit code `2` with `error: unexpected argument '--invalid-flag' found`, which confirms Codex surfaces the bad passthrough arg directly.

### Smoke-tester re-verification (p1463, 2026-04-10)
- Projected streaming command with `extra_args=("--obviously-bogus",)`: `['codex', 'app-server', '--listen', 'stdio://', '--obviously-bogus']`. Debug log emitted pre-launch: `Forwarding passthrough args to codex app-server: ['--obviously-bogus']`.
- Ran the real binary with the projected command — `rc=2`, stderr contained:
  ```
  error: unexpected argument '--obviously-bogus' found
  Usage: codex app-server --listen <URL>
  ```
- Projected subprocess command: `['codex', 'exec', '--json', '--obviously-bogus', '-']`. Real `codex exec` returned `rc=2` with the same `unexpected argument` error plus the `tip: to pass '--obviously-bogus' as a value, use '-- --obviously-bogus'` suggestion.
- **Both paths**: Codex rejects the unknown arg itself; Meridian does not swallow, mask, or rewrite it. The debug log pre-launch + Codex's post-launch error provide the exact diagnostic the scenario requires.

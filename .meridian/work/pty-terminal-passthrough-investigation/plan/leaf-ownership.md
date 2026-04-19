# Leaf Ownership

| EARS ID | Summary | Owner phase | Status | Tester lane | Evidence pointer | Revised |
|---|---|---|---|---|---|---|
| `PTY-01` | terminal signal delivery parity | Phase 3 | blocked | `@smoke-tester` | requires interactive session | no |
| `PTY-02` | initial terminal size at launch | Phase 3 | blocked | `@smoke-tester` | requires interactive session | no |
| `PTY-03` | resize notification after launch | Phase 3 | blocked | `@smoke-tester` | requires interactive session | no |
| `PTY-04` | Ctrl-C interrupt parity | Phase 3 | blocked | `@smoke-tester` | requires interactive session | no |
| `PTY-05` | bidirectional byte passthrough | Phase 3 | blocked | `@smoke-tester` | requires interactive session | no |
| `PTY-06` | raw-mode entry and restoration | Phase 3 | verified-partial | `@smoke-tester` | `stty -a | grep echo` passed after non-PTY path; full PTY path requires interactive | no |
| `PTY-07` | EOF drain behavior | Phase 3 | blocked | `@smoke-tester` | requires interactive session | no |
| `PTY-08` | child exit detection and cleanup | Phase 3 | blocked | `@smoke-tester` | requires interactive session | no |
| `PTY-09` | non-TTY fallback on POSIX | Phase 3 | pre-existing-issue | `@smoke-tester` | root dispatch prints help instead of launching; confirmed pre-existing via git-stash baseline | no |
| `PTY-10` | Windows direct-subprocess fallback | Phase 3 | skip-no-env | `@smoke-tester` | no Windows environment available | no |

## Implementation Verification

| Check | Status | Evidence |
|---|---|---|
| `os.login_tty(slave_fd)` in child path | ✅ verified | `git diff src/meridian/lib/launch/process.py` |
| `os.login_tty` availability | ✅ verified | `hasattr(os, 'login_tty')` = True |
| Import correctness | ✅ verified | `from meridian.lib.launch.process import run_harness_process` succeeds |
| Build health (ruff) | ✅ verified | `uv run ruff check .` passes |
| Build health (pyright) | ✅ verified | `uv run pyright` passes with 0 errors |

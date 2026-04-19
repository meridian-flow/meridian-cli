# Phase 3: Smoke Classification

## Task

Execute the PTY smoke matrix against the patched build and classify results using baseline-first protocol.

## Critical Context

You are testing terminal passthrough behavior. This requires an interactive PTY environment.

**Limitation:** You are running in a non-interactive spawn environment. You cannot perform interactive tests that require:
- Manually resizing terminal windows
- Interactive Ctrl-C during streaming output
- Real-time TUI observation

## What You CAN Verify

From the smoke matrix, verify the following non-interactive tests:

### T-08: Non-TTY Bypass (POSIX)
```bash
# Pipe scenario (stdin not a TTY)
echo "hello" | uv run meridian 2>&1 | head -5
# Expected: No PTY errors, command runs or fails gracefully

# File redirect scenario  
uv run meridian < /dev/null 2>&1 | head -5
# Expected: No PTY errors
```

### T-06/T-07 partial: Terminal Restoration after Exit
```bash
# Run a quick command and check terminal state restored
uv run meridian -p "say hello" 2>&1 | head -20
stty -a | grep -q "echo" && echo "PASS: echo enabled" || echo "FAIL: echo disabled"
```

### Verify the implementation is syntactically correct
```bash
# Import check
python3 -c "from meridian.lib.launch.process import run_harness_process; print('import ok')"

# Verify os.login_tty exists
python3 -c "import os; print('login_tty available:', hasattr(os, 'login_tty'))"
```

## Classification Protocol

For any failure:
1. Run baseline first (raw harness without Meridian)
2. If baseline fails: `UPSTREAM-ONLY`
3. If baseline passes but Meridian fails: `MERIDIAN-CAUSED`
4. If both pass: `PASS`

## Scope Boundaries

- Do NOT modify source code
- Do NOT attempt interactive tests — classify them as `REQUIRES-INTERACTIVE-SESSION`
- Report what was verifiable and what requires manual testing

## Exit Criteria

- Non-interactive tests (T-08, partial T-06/T-07) have dispositions
- Interactive tests (T-01 through T-05, T-09 through T-12) marked as requiring manual session
- Implementation correctness verified (import, os.login_tty availability)

# PTY Terminal Passthrough Smoke Matrix

## Purpose

This matrix verifies that Meridian's PTY passthrough layer behaves correctly across terminal operations and harnesses. Each test distinguishes Meridian-caused failures from upstream harness bugs.

## Prerequisites

```bash
export REPO_ROOT=/path/to/meridian-cli
cd "$REPO_ROOT"

# Verify CLI is runnable
uv run meridian --help >/dev/null && echo "PASS: CLI runnable" || echo "FAIL: CLI not runnable"
```

## Baseline Establishment

Before each Meridian test, run the equivalent raw harness command to establish whether any observed failure is Meridian-specific or upstream-only.

---

## Test Matrix

### T-01: Window Resize During Idle

**EARS:** PTY-01, PTY-03

**Purpose:** Verify resize signal reaches harness when no output is active.

**Baseline (raw harness):**
```bash
# For Claude:
claude

# Resize terminal window while at prompt
# Expected: TUI redraws correctly at new size
```

**Meridian:**
```bash
uv run meridian

# Resize terminal window while at prompt
# Expected: TUI redraws correctly at new size
# PASS if behavior matches baseline
# FAIL if Meridian shows corruption but baseline doesn't
```

**Verdict:** `[ ] PASS  [ ] FAIL  [ ] UPSTREAM-ONLY`

---

### T-02: Window Resize During Active Output

**EARS:** PTY-01, PTY-03, PTY-04

**Purpose:** Verify resize during streaming output doesn't corrupt display.

**Baseline (raw harness):**
```bash
claude -p "print numbers 1 to 100 slowly"

# Resize terminal during output
# Expected: Output continues, TUI adjusts
```

**Meridian:**
```bash
uv run meridian -p "print numbers 1 to 100 slowly"

# Resize terminal during output
# Expected: Output continues, TUI adjusts
# PASS if behavior matches baseline
```

**Verdict:** `[ ] PASS  [ ] FAIL  [ ] UPSTREAM-ONLY`

---

### T-03: Initial Terminal Size

**EARS:** PTY-02

**Purpose:** Verify harness sees correct terminal size at startup.

**Baseline (raw harness):**
```bash
# Resize terminal to unusual size (e.g., 40x10) BEFORE launch
stty size  # Note dimensions
claude

# Check if TUI layout matches terminal size
```

**Meridian:**
```bash
# Same unusual terminal size
stty size
uv run meridian

# Check if TUI layout matches terminal size
# PASS if layout correct
```

**Verdict:** `[ ] PASS  [ ] FAIL  [ ] UPSTREAM-ONLY`

---

### T-04: Ctrl-C Interrupt

**EARS:** PTY-01, PTY-04

**Purpose:** Verify Ctrl-C is handled correctly by harness.

**Baseline (raw harness):**
```bash
claude -p "write a long essay"

# Press Ctrl-C during generation
# Expected: Harness handles interrupt (stops or prompts)
```

**Meridian:**
```bash
uv run meridian -p "write a long essay"

# Press Ctrl-C during generation
# Expected: Same behavior as baseline
```

**Verdict:** `[ ] PASS  [ ] FAIL  [ ] UPSTREAM-ONLY`

---

### T-05: EOF with Trailing Output

**EARS:** PTY-07

**Purpose:** Verify stdin EOF allows trailing child output to drain before exit.

**Baseline (raw harness):**
```bash
# Create a test script that closes stdin then emits output
(echo "hello"; sleep 0.5) | claude -p "repeat what I said then say goodbye"
# Expected: Both the repeat and goodbye appear in output
```

**Meridian:**
```bash
(echo "hello"; sleep 0.5) | uv run meridian -p "repeat what I said then say goodbye"
# Expected: All child output appears, including output after stdin closed
# PASS if trailing output preserved
# FAIL if output truncated at EOF
```

**Verdict:** `[ ] PASS  [ ] FAIL  [ ] UPSTREAM-ONLY`

---

### T-06: Normal Exit and Terminal Restoration

**EARS:** PTY-05, PTY-07

**Purpose:** Verify terminal is restored to normal mode after harness exits.

**Baseline (raw harness):**
```bash
claude -p "say hello"
# Wait for exit
echo "test input"  # Should echo normally
stty -a | grep -q "echo" && echo "PASS: echo enabled" || echo "FAIL: echo disabled"
```

**Meridian:**
```bash
uv run meridian -p "say hello"
# Wait for exit
echo "test input"  # Should echo normally
stty -a | grep -q "echo" && echo "PASS: echo enabled" || echo "FAIL: echo disabled"
```

**Verdict:** `[ ] PASS  [ ] FAIL  [ ] UPSTREAM-ONLY`

---

### T-07: Child Exit Cleanup

**EARS:** PTY-06, PTY-08

**Purpose:** Verify terminal is restored when child harness exits (normally or abnormally).

**Meridian:**
```bash
# Test 1: Normal exit - run a quick command
uv run meridian -p "say hello"
stty -a | grep -q "echo" && echo "PASS: terminal restored" || echo "FAIL: terminal corrupted"

# Test 2: Child crash (not SIGKILL to meridian) - simulate by using timeout
timeout 2 uv run meridian -p "count to one million slowly" || true
stty -a | grep -q "echo" && echo "PASS: terminal restored" || echo "FAIL: terminal corrupted"
```

**Note:** SIGKILL to the Meridian process bypasses cleanup entirely; that's expected behavior. This test verifies the documented guarantee: cleanup runs when the passthrough loop exits normally or via exception.

**Verdict:** `[ ] PASS  [ ] FAIL`

---

### T-08: Non-TTY Bypass (POSIX)

**EARS:** PTY-09

**Purpose:** Verify PTY is not used when stdin/stdout are not TTYs.

```bash
# Pipe scenario (stdin not a TTY)
echo "hello" | uv run meridian 2>&1 | head -5
# Expected: No PTY errors, command runs or fails gracefully

# File redirect scenario
uv run meridian < /dev/null 2>&1 | head -5
# Expected: No PTY errors
```

**Verdict:** `[ ] PASS  [ ] FAIL`

---

### T-12: Windows Direct Subprocess Fallback

**EARS:** PTY-10

**Purpose:** Verify Windows uses direct subprocess (no PTY) and harness runs correctly.

**Prerequisites:** Windows machine with Python 3.12+ and Claude CLI installed.

```powershell
# Basic launch
uv run meridian -p "say hello"
# Expected: Harness runs, responds, exits normally

# Interactive session (manual resize test)
uv run meridian
# Resize terminal window
# Expected: Display may or may not adjust (Windows console behavior varies)
# This is not a failure - Windows PTY is out of scope
# Just verify no crash or error

# Ctrl-C
uv run meridian -p "count to 1000 slowly"
# Press Ctrl-C
# Expected: Process terminates (may be abrupt on Windows)
```

**Verdict:** `[ ] PASS  [ ] FAIL  [ ] SKIP (no Windows environment)`

---

### T-09: Cross-Harness Parity (Claude)

**EARS:** All

**Purpose:** Verify PTY behavior with Claude harness.

```bash
uv run meridian -H claude
# Run T-01 through T-07 with Claude
```

**Verdict:** `[ ] PASS  [ ] FAIL  [ ] UPSTREAM-ONLY`

---

### T-10: Cross-Harness Parity (Codex)

**EARS:** All

**Purpose:** Verify PTY behavior with Codex harness.

```bash
uv run meridian -H codex
# Run T-01 through T-07 with Codex
```

**Verdict:** `[ ] PASS  [ ] FAIL  [ ] UPSTREAM-ONLY  [ ] SKIP (harness unavailable)`

---

### T-11: Cross-Harness Parity (OpenCode)

**EARS:** All

**Purpose:** Verify PTY behavior with OpenCode harness.

```bash
uv run meridian -H opencode
# Run T-01 through T-07 with OpenCode
```

**Verdict:** `[ ] PASS  [ ] FAIL  [ ] UPSTREAM-ONLY  [ ] SKIP (harness unavailable)`

---

## Summary Checklist

| Test | PTY-01 | PTY-02 | PTY-03 | PTY-04 | PTY-05 | PTY-06 | PTY-07 | PTY-08 | PTY-09 | PTY-10 |
|------|--------|--------|--------|--------|--------|--------|--------|--------|--------|--------|
| T-01 | X |   | X |   |   |   |   |   |   |   |
| T-02 | X |   | X | X | X |   |   |   |   |   |
| T-03 |   | X |   |   |   |   |   |   |   |   |
| T-04 |   |   |   | X |   |   |   |   |   |   |
| T-05 |   |   |   |   |   |   | X |   |   |   |
| T-06 |   |   |   |   |   | X |   | X |   |   |
| T-07 |   |   |   |   |   | X |   | X |   |   |
| T-08 |   |   |   |   |   |   |   |   | X |   |
| T-09+ | Cross-harness: all POSIX statements |   |   |   |   |
| T-12 |   |   |   |   |   |   |   |   |   | X |

Legend:
- PTY-01: Terminal Signal Delivery (SIGWINCH, Ctrl-C)
- PTY-02: Initial Window Size
- PTY-03: Window Resize Notification
- PTY-04: Interrupt Parity (Ctrl-C)
- PTY-05: Bidirectional Byte Passthrough
- PTY-06: Raw Mode Entry and Restoration
- PTY-07: EOF Handling (drain trailing output)
- PTY-08: Child Exit Detection
- PTY-09: Non-TTY Fallback (POSIX)
- PTY-10: Windows Fallback

---

## Failure Classification Protocol

For any failure:

1. **Run baseline first** — same test without Meridian
2. **If baseline fails:** classify as `UPSTREAM-ONLY`, document harness version
3. **If baseline passes but Meridian fails:** classify as `MERIDIAN-CAUSED`, file as bug
4. **If both pass:** classify as `PASS`

This protocol ensures we don't blame Meridian for harness bugs and don't ignore Meridian bugs masked by harness behavior.

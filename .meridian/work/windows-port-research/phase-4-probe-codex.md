# Phase 4 Probe: codex termination behavior

## Verdict

For the `codex` harness, both direct-child `SIGTERM` and top-level `killpg` leak the real background grandchild. In both runs, the wrapper and harness binary died, the foreground `sleep 600` died, and the background `sleep 600` survived and was re-parented to PID 1 in its own session/process group. The proposed recursive descendant termination using `psutil` terminated the entire tree and left no survivors.

## Harness invocation

The harness was launched directly in a PTY-backed shell so inline `codex` could keep a real terminal while the shell `exec` made the wrapper PID the top-level `codex` process:

```bash
codex --no-alt-screen --dangerously-bypass-approvals-and-sandbox \
  -C /home/jimyao/gitrepos/meridian-cli \
  "Use exactly one shell command: bash -lc \"sleep 600 </dev/null >/tmp/meridian-pgprobe-codex-<RUN>-grandchild.out 2>&1 & echo \$! > /tmp/meridian-pgprobe-codex-<RUN>-grandchild.pid; sleep 600\". After starting that command, do not interrupt it or run any other shell command."
```

`<RUN>` was `A`, `B`, or `C`. No separate shell PID persisted in the tool subtree; the shell tail-exec'd the foreground `sleep 600`, so the stable subtree was wrapper `codex` -> harness binary `codex` -> foreground `sleep` -> background `sleep`.

## Run A: direct-child SIGTERM

- Process tree before kill:

```text
PID      PPID     PGID     SID      STAT COMMAND    COMMAND
4153123  4135136  4153123  4153123  SNsl+ node      .../bin/codex --no-alt-screen --dangerously-bypass-approvals-and-sandbox -C /home/jimyao/gitrepos/meridian-cli ...
4153135  4153123  4153123  4153123  SNl+  codex     .../vendor/.../codex/codex --no-alt-screen --dangerously-bypass-approvals-and-sandbox -C /home/jimyao/gitrepos/meridian-cli ...
4154300  4153135  4154300  4154300  SNs   sleep     sleep 600
4154305  4154300  4154300  4154300  SN    sleep     sleep 600
```

- Pstree output:

```text
MainThread,4153123 .../bin/codex --no-alt-screen ...
  |-codex,4153135
  |   |-sleep,4154300 600
  |   |   `-sleep,4154305 600
  |   `-{codex threads...}
  `-{MainThread threads...}
```

- Kill command:

```bash
kill -TERM 4153123
```

- Survivors after 3s:

```text
PID      PPID  PGID     SID      STAT COMMAND  COMMAND
4154305  1     4154300  4154300  SN   sleep    sleep 600
```

- Interpretation:

Direct-child `SIGTERM` is insufficient. The wrapper and harness binary die, but the real background grandchild survives because it had already moved into the foreground tool process's own session/process group and outlived the parent chain.

## Run B: top-level killpg

- Process tree before kill:

```text
PID      PPID     PGID     SID      STAT COMMAND    COMMAND
4156109  4135136  4156109  4156109  SNsl+ node      .../bin/codex --no-alt-screen --dangerously-bypass-approvals-and-sandbox -C /home/jimyao/gitrepos/meridian-cli ...
4156215  4156109  4156109  4156109  SNl+  codex     .../vendor/.../codex/codex --no-alt-screen --dangerously-bypass-approvals-and-sandbox -C /home/jimyao/gitrepos/meridian-cli ...
4157625  4156215  4157625  4157625  SNs   sleep     sleep 600
4157630  4157625  4157625  4157625  SN    sleep     sleep 600
```

- Pstree output:

```text
MainThread,4156109 .../bin/codex --no-alt-screen ...
  |-codex,4156215
  |   |-sleep,4157625 600
  |   |   `-sleep,4157630 600
  |   `-{codex threads...}
  `-{MainThread threads...}
```

- Kill command:

```bash
kill -TERM -4156109
```

- Survivors after 3s:

```text
PID      PPID  PGID     SID      STAT COMMAND  COMMAND
4157630  1     4157625  4157625  SN   sleep    sleep 600
```

- Interpretation:

Current Unix-style top-level `killpg(top_pgid)` is also insufficient for `codex`. The top-level wrapper group dies, but the long-lived tool subtree had already broken away into its own session/process group (`pgid=sid=4157625`), so the deepest descendant survives exactly as in Run A.

## Run C: psutil recursive terminate

- Process tree before kill:

```text
PID      PPID     PGID     SID      STAT COMMAND    COMMAND
4159472  4135136  4159472  4159472  SNsl+ node      .../bin/codex --no-alt-screen --dangerously-bypass-approvals-and-sandbox -C /home/jimyao/gitrepos/meridian-cli ...
4159484  4159472  4159472  4159472  SNl+  codex     .../vendor/.../codex/codex --no-alt-screen --dangerously-bypass-approvals-and-sandbox -C /home/jimyao/gitrepos/meridian-cli ...
4161268  4159484  4161268  4161268  SNs   sleep     sleep 600
4161273  4161268  4161268  4161268  SN    sleep     sleep 600
```

- Pstree output:

```text
MainThread,4159472 .../bin/codex --no-alt-screen ...
  |-codex,4159484
  |   |-sleep,4161268 600
  |   |   `-sleep,4161273 600
  |   `-{codex threads...}
  `-{MainThread threads...}
```

- Kill command:

```bash
uv run python -c "
import psutil, time, sys
root = psutil.Process(int(sys.argv[1]))
descendants = root.children(recursive=True)
all_procs = [root, *descendants]
for p in all_procs:
    try: p.terminate()
    except psutil.NoSuchProcess: pass
gone, alive = psutil.wait_procs(all_procs, timeout=3)
for p in alive:
    try: p.kill()
    except psutil.NoSuchProcess: pass
" 4159472
```

- Survivors after 3s:

```text
PID      PPID     PGID     SID      STAT COMMAND    COMMAND
(none)
```

- Interpretation:

Recursive descendant termination matches the desired semantics for this harness. Starting from the wrapper PID was enough to enumerate and terminate the harness binary, the foreground tool process, and the detached background grandchild.

## Cross-cuts vs Codex probe

- Same pattern as the existing Phase 4 probe: direct-child `SIGTERM` leaks the background grandchild, and top-level `killpg` also leaks it.
- The detached tool subtree still forms its own session/process group under `codex` inline mode, so process-group signaling at the wrapper boundary is not enough.
- This strengthens the case for a shared `terminate_tree(proc, grace)` primitive on both Unix and Windows instead of preserving top-level `killpg` as the semantic target.

## Confidence

High. All three runs used real `codex` executions with real PIDs and real descendant trees, and the leak/non-leak outcomes were consistent across fresh launches. The only nuance is that no separate shell PID persisted in the subtree because Bash tail-exec'd the foreground `sleep`; that changes the visible tree shape slightly, but not the termination result.

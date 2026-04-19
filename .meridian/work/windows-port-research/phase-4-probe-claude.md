# Phase 4 Probe: claude termination behavior

## Verdict

For `claude`, both direct-child `SIGTERM` and top-level `killpg(top_pgid)` leak the real Bash tool subtree. In both runs, the top `claude` process died, but the Bash tool wrapper plus both `sleep 600` descendants survived and were re-parented to PID 1. A recursive descendant walk using `psutil.Process.children(recursive=True)` terminated the full tree cleanly. That makes the proposed Phase 4 `terminate_tree(proc, grace)` refactor necessary for `claude` too, not just for Codex.

## Harness invocation

Non-interactive harness command used for all three runs:

```bash
setsid claude -p \
  --permission-mode bypassPermissions \
  --tools Bash \
  --output-format json \
  --strict-mcp-config \
  --mcp-config /tmp/meridian-pgprobe-claude-<RUN>-mcp.json \
  --add-dir /home/jimyao/gitrepos/meridian-cli \
  < /tmp/meridian-pgprobe-claude-<RUN>.prompt
```

Prompt contents:

```text
Use exactly one Bash command: bash -lc "sleep 600 </dev/null >/tmp/meridian-pgprobe-claude-<RUN>-grandchild.out 2>&1 & echo \$! > /tmp/meridian-pgprobe-claude-<RUN>-grandchild.pid; sleep 600". After starting that command, do not interrupt it or run any other shell command.
```

Notes:

- `setsid` was required so the top `claude` process matched Meridian's Unix launch shape (`pid == pgid == sid`).
- `claude --bare` was not usable here because it disables OAuth/keychain auth and failed with `Not logged in · Please run /login`.
- To suppress unrelated MCP helper processes without losing auth, the probe used `--strict-mcp-config` with an empty config file: `{"mcpServers":{}}`.

## Run A: direct-child SIGTERM

- Process tree before kill:

```text
    PID    PPID    PGID     SID STAT COMMAND         COMMAND
4155042 4155038 4155042 4155042 SNsl claude          claude -p --permission-mode bypassPermissions --tools Bash --output-format json --strict-mcp-config --mcp-config /tmp/meridian-pgprobe-claude-A-mcp.json --add-dir /home/jimyao/gitrepos/meridian-cli
4155579 4155042 4155579 4155579 SNs  bash            /bin/bash -c source /home/jimyao/.claude/shell-snapshots/snapshot-bash-1776397410725-c2x1zw.sh 2>/dev/null || true && shopt -u extglob 2>/dev/null || true && eval 'bash -lc "sleep 600 </dev/null >/tmp/meridian-pgprobe-claude-A-grandchild.out 2>&1 & echo \$! > /tmp/meridian-pgprobe-claude-A-grandchild.pid; sleep 600"' && pwd -P >| /tmp/claude-6d76-cwd
4155581 4155579 4155581 4155579 SN   sleep           sleep 600
4155586 4155581 4155581 4155579 SN   sleep           sleep 600
```

- Pstree output:

```text
claude,4155042 -p --permission-mode bypassPermissions --tools Bash --output-format json --strict-mcp-config --mcp-config...
  |-bash,4155579 -c...
  |   `-sleep,4155581 600
  |       `-sleep,4155586 600
  |-{claude},4155045
  |-{claude},4155046
  |-{claude},4155047
  |-{claude},4155048
  |-{claude},4155049
  |-{claude},4155050
  |-{claude},4155051
  |-{claude},4155052
  |-{claude},4155053
  |-{claude},4155054
  |-{claude},4155055
  |-{claude},4155056
  |-{claude},4155057
  |-{claude},4155058
  |-{claude},4155059
  |-{claude},4155060
  |-{claude},4155061
  |-{claude},4155062
  |-{claude},4155065
  |-{claude},4155066
  |-{claude},4155072
  |-{claude},4155087
  |-{claude},4155088
  |-{claude},4155089
  |-{claude},4155090
  |-{claude},4155091
  |-{claude},4155092
  |-{claude},4155093
  |-{claude},4155094
  |-{claude},4155095
  |-{claude},4155096
  |-{claude},4155097
  |-{claude},4155098
  |-{claude},4155099
  |-{claude},4155100
  |-{claude},4155101
  `-{claude},4155102
```

- Kill command:

```bash
kill -TERM 4155042
```

- Survivors after 2s:

```text
    PID    PPID    PGID     SID STAT COMMAND         COMMAND
4155579       1 4155579 4155579 SNs  bash            /bin/bash -c source /home/jimyao/.claude/shell-snapshots/snapshot-bash-1776397410725-c2x1zw.sh 2>/dev/null || true && shopt -u extglob 2>/dev/null || true && eval 'bash -lc "sleep 600 </dev/null >/tmp/meridian-pgprobe-claude-A-grandchild.out 2>&1 & echo \$! > /tmp/meridian-pgprobe-claude-A-grandchild.pid; sleep 600"' && pwd -P >| /tmp/claude-6d76-cwd
4155581 4155579 4155581 4155579 SN   sleep           sleep 600
4155586 4155581 4155581 4155579 SN   sleep           sleep 600
```

- Interpretation:

Direct-child `SIGTERM` killed the top `claude` process only. The Bash tool subtree had already moved into its own session/process groups and remained alive as an orphaned subtree under PID 1.

## Run B: top-level killpg

- Process tree before kill:

```text
    PID    PPID    PGID     SID STAT COMMAND         COMMAND
4157305 4157301 4157305 4157305 SNsl claude          claude -p --permission-mode bypassPermissions --tools Bash --output-format json --strict-mcp-config --mcp-config /tmp/meridian-pgprobe-claude-B-mcp.json --add-dir /home/jimyao/gitrepos/meridian-cli
4157652 4157305 4157652 4157652 SNs  bash            /bin/bash -c source /home/jimyao/.claude/shell-snapshots/snapshot-bash-1776397434931-kr8n9q.sh 2>/dev/null || true && shopt -u extglob 2>/dev/null || true && eval 'bash -lc "sleep 600 </dev/null >/tmp/meridian-pgprobe-claude-B-grandchild.out 2>&1 & echo \$! > /tmp/meridian-pgprobe-claude-B-grandchild.pid; sleep 600"' && pwd -P >| /tmp/claude-66c0-cwd
4157654 4157652 4157654 4157652 SN   sleep           sleep 600
4157660 4157654 4157654 4157652 SN   sleep           sleep 600
```

- Pstree output:

```text
claude,4157305 -p --permission-mode bypassPermissions --tools Bash --output-format json --strict-mcp-config --mcp-config...
  |-bash,4157652 -c...
  |   `-sleep,4157654 600
  |       `-sleep,4157660 600
  |-{claude},4157308
  |-{claude},4157309
  |-{claude},4157310
  |-{claude},4157311
  |-{claude},4157312
  |-{claude},4157313
  |-{claude},4157314
  |-{claude},4157315
  |-{claude},4157316
  |-{claude},4157317
  |-{claude},4157319
  |-{claude},4157320
  |-{claude},4157321
  |-{claude},4157322
  |-{claude},4157323
  |-{claude},4157324
  |-{claude},4157327
  |-{claude},4157328
  |-{claude},4157329
  |-{claude},4157335
  |-{claude},4157336
  |-{claude},4157351
  |-{claude},4157352
  |-{claude},4157353
  |-{claude},4157354
  |-{claude},4157355
  |-{claude},4157356
  `-{claude},4157357
```

- Kill command:

```bash
kill -TERM -4157305
```

- Survivors after 2s:

```text
    PID    PPID    PGID     SID STAT COMMAND         COMMAND
4157652       1 4157652 4157652 SNs  bash            /bin/bash -c source /home/jimyao/.claude/shell-snapshots/snapshot-bash-1776397434931-kr8n9q.sh 2>/dev/null || true && shopt -u extglob 2>/dev/null || true && eval 'bash -lc "sleep 600 </dev/null >/tmp/meridian-pgprobe-claude-B-grandchild.out 2>&1 & echo \$! > /tmp/meridian-pgprobe-claude-B-grandchild.pid; sleep 600"' && pwd -P >| /tmp/claude-66c0-cwd
4157654 4157652 4157654 4157652 SN   sleep           sleep 600
4157660 4157654 4157654 4157652 SN   sleep           sleep 600
```

- Interpretation:

Top-level `killpg(top_pgid)` was also insufficient. The Bash tool subtree had already moved into its own session/process groups, so signaling `pgid=4157305` reached the top `claude` process but not the live tool subtree.

## Run C: psutil recursive terminate

- Process tree before kill:

```text
    PID    PPID    PGID     SID STAT COMMAND         COMMAND
4158573 4158569 4158573 4158573 SNsl claude          claude -p --permission-mode bypassPermissions --tools Bash --output-format json --strict-mcp-config --mcp-config /tmp/meridian-pgprobe-claude-C-mcp.json --add-dir /home/jimyao/gitrepos/meridian-cli
4159105 4158573 4159105 4159105 SNs  bash            /bin/bash -c source /home/jimyao/.claude/shell-snapshots/snapshot-bash-1776397461618-oypyok.sh 2>/dev/null || true && shopt -u extglob 2>/dev/null || true && eval 'bash -lc "sleep 600 </dev/null >/tmp/meridian-pgprobe-claude-C-grandchild.out 2>&1 & echo \$! > /tmp/meridian-pgprobe-claude-C-grandchild.pid; sleep 600"' && pwd -P >| /tmp/claude-2925-cwd
4159107 4159105 4159107 4159105 SN   sleep           sleep 600
4159112 4159107 4159107 4159105 SN   sleep           sleep 600
```

- Pstree output:

```text
claude,4158573 -p --permission-mode bypassPermissions --tools Bash --output-format json --strict-mcp-config --mcp-config...
  |-bash,4159105 -c...
  |   `-sleep,4159107 600
  |       `-sleep,4159112 600
  |-{claude},4158576
  |-{claude},4158577
  |-{claude},4158578
  |-{claude},4158579
  |-{claude},4158580
  |-{claude},4158581
  |-{claude},4158582
  |-{claude},4158583
  |-{claude},4158584
  |-{claude},4158585
  |-{claude},4158586
  |-{claude},4158587
  |-{claude},4158588
  |-{claude},4158589
  |-{claude},4158590
  |-{claude},4158591
  |-{claude},4158594
  |-{claude},4158595
  |-{claude},4158601
  |-{claude},4158602
  |-{claude},4158617
  |-{claude},4158618
  |-{claude},4158619
  |-{claude},4158620
  |-{claude},4158621
  |-{claude},4158622
  |-{claude},4158623
  |-{claude},4158624
  |-{claude},4158625
  |-{claude},4158626
  |-{claude},4158627
  |-{claude},4158628
  `-{claude},4158629
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
" 4158573
```

- Survivors after 2s:

```text
    PID    PPID    PGID     SID STAT COMMAND         COMMAND
```

- Interpretation:

Recursive descendant termination reached the `claude` root, the Bash tool wrapper, and both `sleep` descendants. No tracked process survived.

## Cross-cuts vs Codex probe

- Same high-level conclusion as [`phase-4-probe.md`](./phase-4-probe.md): direct-child `SIGTERM` is insufficient, and top-level `killpg(top_pgid)` is also insufficient once tool descendants create their own session/process groups.
- Different leak shape from Codex: in the Claude probe, the leaked subtree was the Bash tool wrapper plus both `sleep` descendants, not just the deepest `sleep`.
- The proposed `psutil`-based `terminate_tree` primitive covers both harnesses with one model: enumerate descendants from the launched root and terminate the actual tree, not just the original process group.

## Confidence

High. This used three real `claude` runs with real PIDs, real session/process-group metadata from `ps`, and real tree shape from `pstree`. The only meaningful caveat is that descendant layout may vary for other tool commands, but this probe is sufficient to prove that group-based termination is not a safe universal strategy for `claude`.

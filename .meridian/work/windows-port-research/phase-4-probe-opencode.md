# Phase 4 Probe: opencode termination behavior

## Verdict

`opencode` shows the same core failure mode as the Codex probe, but more strongly. Once the tool command starts, the long-lived tool subtree moves into its own session/process group. Sending `SIGTERM` only to the direct child wrapper leaks both the foreground and background `sleep` processes. Sending `SIGTERM` to the top-level process group (`kill -TERM -<wrapper_pid>`) also leaks both sleeps, because that group no longer contains the tool subtree. Recursive descendant termination via `psutil` removed the entire tree. This supports the proposed `terminate_tree(proc, grace)` refactor and argues against treating current Unix `killpg(top_pgid)` behavior as sufficient.

## Harness invocation

Steady-state harness command used in all three runs:

```bash
opencode run --dangerously-skip-permissions --dir /home/jimyao/gitrepos/meridian-cli \
  'Use exactly one shell command: bash -lc "sleep 600 </dev/null >/tmp/meridian-pgprobe-opencode-<RUN>-grandchild.out 2>&1 & echo $! > /tmp/meridian-pgprobe-opencode-<RUN>-grandchild.pid; sleep 600". After starting that command, do not interrupt it or run any other shell command.'
```

For PID labeling, each run was launched from:

```bash
bash -lc 'printf "WRAPPERPID:%s\n" $$; exec opencode run ...'
```

Observed runtime banner in each run:

```text
> build · minimax-m2.5-free
```

Note: unlike the Codex probe, `opencode` did not leave a distinct harness-binary child in steady state. The wrapper PID was the live `opencode` process. No persistent shell PID remained after the tool command started; the direct child under `opencode` had already exec'd into the foreground `sleep`.

## Run A: direct-child SIGTERM

- Wrapper PID: `4153002`
- Foreground tool PID: `4153348`
- Background tool PID (from pid file): `4153349`

Process table before kill:

```text
PID      PPID     PGID      SID   STAT COMMAND  COMMAND
4153002  4146803  4153002   4153002 SNsl+ opencode opencode run --dangerously-skip-permissions --dir /home/jimyao/gitrepos/meridian-cli Use exactly one shell command: bash -lc "sleep 600 </dev/null >/tmp/meridian-pgprobe-opencode-A-grandchild.out 2>&1 & echo $! > /tmp/meridian-pgprobe-opencode-A-grandchild.pid; sleep 600". After starting that command, do not interrupt it or run any other shell command.
4153348  4153002  4153348   4153348 SNs   sleep    sleep 600
4153349  4153348  4153348   4153348 SN    sleep    sleep 600
```

Pstree before kill:

```text
opencode,4153002 run --dangerously-skip-permissions --dir /home/jimyao/gitrepos/meridian-cli...
  |-sleep,4153348 600
  |   `-sleep,4153349 600
  |-{opencode},4153010
  |-{opencode},4153011
  |-{opencode},4153012
  |-{opencode},4153013
  |-{opencode},4153014
  |-{opencode},4153015
  |-{opencode},4153016
  |-{opencode},4153017
  |-{opencode},4153018
  |-{opencode},4153019
  |-{opencode},4153021
  |-{opencode},4153022
  |-{opencode},4153023
  |-{opencode},4153024
  |-{opencode},4153025
  |-{opencode},4153026
  |-{opencode},4153027
  |-{opencode},4153028
  |-{opencode},4153029
  |-{opencode},4153030
  |-{opencode},4153031
  |-{opencode},4153032
  |-{opencode},4153033
  |-{opencode},4153034
  |-{opencode},4153035
  |-{opencode},4153036
  |-{opencode},4153037
  |-{opencode},4153038
  |-{opencode},4153039
  |-{opencode},4153040
  |-{opencode},4153041
  |-{opencode},4153042
  |-{opencode},4153043
  |-{opencode},4153044
  |-{opencode},4153045
  |-{opencode},4153046
  |-{opencode},4153047
  |-{opencode},4153068
  |-{opencode},4153069
  |-{opencode},4153071
  |-{opencode},4153072
  |-{opencode},4153073
  |-{opencode},4153074
  |-{opencode},4153075
  `-{opencode},4153076
```

Kill command:

```bash
kill -TERM 4153002
```

Survivors after 2s:

```text
PID      PPID     PGID      SID   STAT COMMAND  COMMAND
4153348  1        4153348   4153348 SNs  sleep    sleep 600
4153349  4153348  4153348   4153348 SN   sleep    sleep 600
```

Interpretation:

The direct-child signal killed `opencode` only. The tool subtree was already in its own session/process group (`pgid=sid=4153348`), so both the foreground and background `sleep` processes survived and were reparented.

## Run B: top-level killpg

- Wrapper PID: `4159942`
- Foreground tool PID: `4160726`
- Background tool PID (from pid file): `4160728`

Process table before kill:

```text
PID      PPID     PGID      SID   STAT COMMAND  COMMAND
4159942  4146803  4159942   4159942 SNsl+ opencode opencode run --dangerously-skip-permissions --dir /home/jimyao/gitrepos/meridian-cli Use exactly one shell command: bash -lc "sleep 600 </dev/null >/tmp/meridian-pgprobe-opencode-B-grandchild.out 2>&1 & echo $! > /tmp/meridian-pgprobe-opencode-B-grandchild.pid; sleep 600". After starting that command, do not interrupt it or run any other shell command.
4160726  4159942  4160726   4160726 SNs   sleep    sleep 600
4160728  4160726  4160726   4160726 SN    sleep    sleep 600
```

Pstree before kill:

```text
opencode,4159942 run --dangerously-skip-permissions --dir /home/jimyao/gitrepos/meridian-cli...
  |-sleep,4160726 600
  |   `-sleep,4160728 600
  |-{opencode},4159950
  |-{opencode},4159951
  |-{opencode},4159952
  |-{opencode},4159953
  |-{opencode},4159954
  |-{opencode},4159955
  |-{opencode},4159956
  |-{opencode},4159957
  |-{opencode},4160032
  |-{opencode},4160034
  |-{opencode},4160117
  |-{opencode},4160127
  |-{opencode},4160128
  |-{opencode},4160129
  |-{opencode},4160223
  |-{opencode},4160224
  |-{opencode},4160225
  |-{opencode},4160226
  |-{opencode},4160227
  |-{opencode},4160228
  |-{opencode},4160229
  |-{opencode},4160230
  |-{opencode},4160231
  |-{opencode},4160232
  |-{opencode},4160233
  |-{opencode},4160234
  |-{opencode},4160235
  |-{opencode},4160236
  |-{opencode},4160237
  |-{opencode},4160238
  |-{opencode},4160239
  |-{opencode},4160240
  |-{opencode},4160241
  |-{opencode},4160242
  |-{opencode},4160243
  |-{opencode},4160244
  |-{opencode},4160245
  |-{opencode},4160300
  |-{opencode},4160301
  |-{opencode},4160304
  |-{opencode},4160305
  |-{opencode},4160306
  |-{opencode},4160307
  |-{opencode},4160308
  |-{opencode},4160309
  `-{opencode},4160311
```

Kill command:

```bash
kill -TERM -4159942
```

Survivors after 2s:

```text
PID      PPID     PGID      SID   STAT COMMAND  COMMAND
4160726  1        4160726   4160726 SNs  sleep    sleep 600
4160728  4160726  4160726   4160726 SN   sleep    sleep 600
```

Interpretation:

Current Unix-style `killpg(top_pgid)` is not sufficient for `opencode`. The tool subtree had already moved into its own session/process group (`pgid=sid=4160726`), so signaling the wrapper's group never reached either `sleep`.

## Run C: psutil recursive terminate

- Wrapper PID: `4161620`
- Foreground tool PID: `4162005`
- Background tool PID (from pid file): `4162006`

Process table before kill:

```text
PID      PPID     PGID      SID   STAT COMMAND  COMMAND
4161620  4146803  4161620   4161620 SNsl+ opencode opencode run --dangerously-skip-permissions --dir /home/jimyao/gitrepos/meridian-cli Use exactly one shell command: bash -lc "sleep 600 </dev/null >/tmp/meridian-pgprobe-opencode-C-grandchild.out 2>&1 & echo $! > /tmp/meridian-pgprobe-opencode-C-grandchild.pid; sleep 600". After starting that command, do not interrupt it or run any other shell command.
4162005  4161620  4162005   4162005 SNs   sleep    sleep 600
4162006  4162005  4162005   4162005 SN    sleep    sleep 600
```

Pstree before kill:

```text
opencode,4161620 run --dangerously-skip-permissions --dir /home/jimyao/gitrepos/meridian-cli...
  |-sleep,4162005 600
  |   `-sleep,4162006 600
  |-{opencode},4161626
  |-{opencode},4161627
  |-{opencode},4161628
  |-{opencode},4161629
  |-{opencode},4161630
  |-{opencode},4161631
  |-{opencode},4161632
  |-{opencode},4161633
  |-{opencode},4161635
  |-{opencode},4161636
  |-{opencode},4161637
  |-{opencode},4161638
  |-{opencode},4161639
  |-{opencode},4161640
  |-{opencode},4161641
  |-{opencode},4161642
  |-{opencode},4161643
  |-{opencode},4161644
  |-{opencode},4161645
  |-{opencode},4161646
  |-{opencode},4161647
  |-{opencode},4161648
  |-{opencode},4161649
  |-{opencode},4161650
  |-{opencode},4161651
  |-{opencode},4161652
  |-{opencode},4161653
  |-{opencode},4161654
  |-{opencode},4161655
  |-{opencode},4161656
  |-{opencode},4161657
  |-{opencode},4161658
  |-{opencode},4161659
  |-{opencode},4161660
  |-{opencode},4161661
  |-{opencode},4161662
  |-{opencode},4161663
  |-{opencode},4161682
  |-{opencode},4161700
  |-{opencode},4161701
  |-{opencode},4161707
  |-{opencode},4161708
  `-{opencode},4161710
```

Kill command:

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
" 4161620
```

Survivors after 2s:

```text
<none>
```

Interpretation:

Enumerating descendants recursively from the wrapper PID and terminating the whole set removed both the wrapper and the re-parentable tool subtree. This matched the intended Phase 4 `terminate_tree(proc, grace)` semantics.

## Cross-cuts vs Codex probe

- Same core result: direct-child `SIGTERM` is insufficient, and top-level `killpg(top_pgid)` is also insufficient once the harness-created tool subtree moves into its own session/process group.
- Stronger than Codex: in the earlier Codex probe, the deepest grandchild survived while the immediate foreground `sleep` died. Under `opencode`, both the foreground and background `sleep` processes survived in Runs A and B.
- Mechanically, `opencode` behaved like a direct wrapper process with the tool subtree detached below it. There was no distinct long-lived child harness binary to signal separately.
- This strengthens the case that Phase 4 should converge on recursive descendant termination as the primitive for both Unix and Windows, rather than preserving current Unix `killpg(top_pgid)` semantics and only shimming Windows.

## Confidence

High. All three runs used real `opencode` invocations, real PID files, real `ps`/`pstree` capture, and real termination signals. The direct-child leak and top-level killpg leak both reproduced cleanly on fresh PIDs, and recursive descendant termination left no survivors.

# Investigation B-06: `spawn wait` returned before target finalized

## Summary

I traced the code path used by the installed `meridian` binary and compared it
to the live `p1861`/`p1843`/`p1844` state.

Verdict: I could **not** confirm a bug in Meridian's `spawn wait` loop itself.
For the same resolved repo/state root and the same spawn id, the current
implementation can only return success after it sees a **terminal projected
status**. That path would require a terminal row in `.meridian/spawns.jsonl`.
For `p1861`, `p1843`, and `p1844`, there is no such finalize row and `spawn
show` still reports `running`, so the observed "completed" signal did **not**
come from the normal `spawn_wait_sync()` success path against those live rows.

Highest-confidence diagnosis: the spurious completion came from the
**caller/background-task layer** (or a mismatched resolved repo/state root),
not from `spawn_wait_sync()` deciding that the target spawn was finished.

## What I checked

- Repo orientation:
  - `meridian work` shows `p1843`, `p1844`, `p1861`, `p1867`, `p1868` still active.
- Live state:
  - `meridian spawn show p1861` -> `Status: running`
  - `meridian spawn show p1843` -> `Status: running`
  - `meridian spawn show p1844` -> `Status: running`
  - `p1861` heartbeat is recent and `output.jsonl` is still growing.
  - Tail of `.meridian/spawns.jsonl` contains no `finalize` event for `p1861`.
- Installed binary code, not just the checkout:
  - `which meridian` -> `/home/jimyao/.local/bin/meridian`
  - Installed package path:
    `/home/jimyao/.local/share/uv/tools/meridian-cli/lib/python3.14/site-packages/meridian/...`
  - Installed code matches the current source for the relevant functions.

## Exact wait code path

Installed code references:

- `meridian/lib/ops/spawn/api.py:580-647`
- `meridian/lib/ops/spawn/query.py:67-73`
- `meridian/lib/state/spawn_store.py:648-681`
- `meridian/lib/state/reaper.py:145-179`
- `meridian/lib/state/reaper.py:251-265`
- `meridian/lib/core/spawn_lifecycle.py:13-24`

### 1. `spawn wait` only exits successfully on terminal status

`spawn_wait_sync()` polls `read_spawn_row()` and only removes a spawn from the
pending set when `_spawn_is_terminal(row.status)` is true.

- `api.py:613-621`:
  - read row
  - if status is terminal -> mark complete
- `api.py:623-632`:
  - return only when `pending` is empty

Terminal statuses are only `succeeded`, `failed`, `cancelled`:

- `spawn_lifecycle.py:13-24`

There is no success path based on:

- child completion
- `output.jsonl` event types
- `exited_at`
- `process_exit_code`
- idle/heartbeat alone

### 2. `read_spawn_row()` rereads store state each poll

`read_spawn_row()` does not cache rows. It:

1. projects the current row from `spawns.jsonl`
2. if active, runs read-path reconciliation

- `query.py:67-73`
- `spawn_store.py:648-681`

This falsifies the "wait is reading stale cached state" hypothesis.

### 3. Reaper reconciliation cannot silently fake a terminal row

If reconciliation decides a row is terminal, it calls `finalize_spawn(...)`
with `origin="reconciler"`:

- `reaper.py:182-199`
- `reaper.py:251-265`

That appends a real `finalize` event under the spawn-store lock:

- `spawn_store.py:325-352`

So if `spawn wait` had returned because reaper stamped the row terminal, there
would be a `finalize` line in `.meridian/spawns.jsonl`. For `p1861`, there
isn't.

That falsifies the "brief heartbeat staleness made wait think the spawn was
terminal" hypothesis for the observed `p1861` case.

## Hypothesis evaluation

### Hypothesis: wait returns when reaper transiently marks terminal

Status: **falsified for the observed case**

Reason:

- reaper terminalization writes a real `finalize` row
- no `finalize` row exists for `p1861`
- `p1861` heartbeat is recent and `spawn show` still reports `running`

### Hypothesis: wait reads stale state from `spawns.jsonl`

Status: **falsified**

Reason:

- `spawn_wait_sync()` rereads via `read_spawn_row()` every poll
- `get_spawn()` rebuilds the projection from the JSONL file on each read
- no memoized wait-state cache exists on this path

### Hypothesis: wait terminates when a child finalizes

Status: **falsified**

Reason:

- `spawn_wait_sync()` only checks the requested `spawn_id`
- no descendant traversal occurs on the wait path

### Hypothesis: wait watches `output.jsonl` event types directly

Status: **falsified**

Reason:

- wait never parses `output.jsonl`
- reaper only uses artifact mtimes and `report.md` durable-completion check

## Strong negative result

For one resolved repo root, one resolved state root, and one literal spawn id,
the current implementation cannot produce this exact combination:

1. `meridian spawn wait p1861` exits `0`
2. `p1861` still projects `status=running`
3. `p1861` has no `finalize` event

If (1) really happened against the same live row, then either:

- the observed "completed" signal was **not** the return from
  `spawn_wait_sync()` for that row, or
- the command resolved a **different repo/state root** than the later
  `spawn show`

## Live evidence pointing outside `spawn_wait_sync`

Inside long-running spawn `p1861`, Claude backgrounded:

- `meridian spawn wait p1867`

I found the actual background processes still alive:

- `/bin/bash -c ... eval 'meridian spawn wait p1867' ...`
- child Python `.../meridian spawn wait p1867`

At the same time:

- `p1867` still projects `running`
- the background task output file for that wait is still empty

That is consistent with Meridian wait behaving normally: it is still blocked.
This does **not** reproduce the claimed early-return bug on the actual wait
code path.

Separately, `p1861/output.jsonl` shows Claude emits its own background task
notifications (`task_started`, `task_updated`, `task_notification`) around
shell commands. Those notifications are a distinct lifecycle layer from the
Meridian spawn state machine.

## Most likely mechanism

I cannot pin the exact completed notification without the top-level session log
that ran `wait p1861`, but the highest-confidence explanation is:

1. the user/caller saw a **background task completion signal from the harness
   layer**
2. that signal was interpreted as "the target spawn finished"
3. but the Meridian row for `p1861` never went terminal

The fallback explanation is repo/state-root mismatch:

- `spawn wait` resolves repo root via explicit arg, then
  `MERIDIAN_REPO_ROOT`, then CWD ancestry
  (`config/settings.py:802-835`)
- state root can also be redirected by `MERIDIAN_STATE_ROOT`
  (`state/paths.py:105-115`)

If those differed between the background wait command and the later
`spawn show`, the two commands could have been reading different state.

## Reproduction notes

I did **not** reproduce an actual early successful return from
`spawn_wait_sync()` against a still-running row.

I **did** reproduce the opposite:

- a real `meridian spawn wait p1867` process remains alive while `p1867`
  is still `running`

So the concrete `p1861` symptom needs one more artifact to close the loop:

- the top-level harness/session log or captured stdout/stderr for the exact
  backgrounded `meridian spawn wait p1861` command

Without that, the caller/background-layer explanation is strongest but not
fully proven.

## Fix recommendation

### Immediate recommendation

Treat B-06 as **not yet proven inside Meridian wait logic**. Investigate the
caller/background-task layer next.

### Instrumentation to add

1. Make `spawn wait` print or log the resolved `repo_root`, `state_root`, and
   literal `spawn_id` at start in verbose/debug mode.
2. On successful return, print the terminal evidence used:
   `status`, `finished_at`, `terminal_origin`.
3. Add a debug log line in `spawn_wait_sync()` each time a spawn leaves
   `pending`, so a captured wait transcript shows exactly why it exited.
4. In the harness/background-task layer, include the wrapped command's actual
   stdout payload in the completion notification or preserve the `.output`
   artifact reliably.

### If the goal is to make this class of confusion impossible

Add a lightweight invariant check at the caller boundary:

- only treat `spawn wait` success as authoritative if the returned payload
  includes a terminal status for the requested spawn id

That would prevent a generic "background command completed" signal from being
mistaken for "the target spawn finalized."

## Issue tracking

I did not create a GitHub issue.

Reason:

- this investigation is already scoped under the existing
  `spawn-finalize-bugs` work item
- the root cause is not yet specific enough to justify a separate external
  issue beyond the existing tracked bug bucket

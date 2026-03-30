# Spawn Debugging

Read this only when something looks wrong: a spawn seems stuck, expected output is missing, `show` and `wait` disagree with what you expected, or you need to inspect low-level state.

## First Checks

Start with the normal read path:

```bash
meridian spawn show SPAWN_ID
meridian spawn wait SPAWN_ID
meridian spawn list --all
```

Use `show` first to inspect the persisted state for one spawn. Use `wait` if the spawn may still be running. Use `list --all` for situational awareness, not as your primary lookup path.

## Logs

Each spawn records a stderr log under the Meridian state root. Prefer getting the path from `spawn show` output instead of constructing it manually.

```bash
meridian spawn show SPAWN_ID
# Look for "log_path" in the JSON output.
```

If you already know the resolved state root, the log is typically at:

```text
$MERIDIAN_STATE_ROOT/spawns/SPAWN_ID/stderr.log
```

Tail a running log only when you need detailed harness traces:

```bash
tail -f "$MERIDIAN_STATE_ROOT/spawns/SPAWN_ID/stderr.log"
```

## Shared Files

If a workflow depends on handoff files, inspect `MERIDIAN_FS_DIR`.

```bash
ls -la "$MERIDIAN_FS_DIR"
```

## Stuck Spawn Recovery

Meridian reconciles running spawns on read. If a process died, wrote a report without finalizing, or went stale, the next `spawn list`, `spawn show`, `spawn wait`, or `meridian doctor` call detects that and marks it failed.

If a spawn seems stuck, run:

```bash
meridian spawn list --all
meridian doctor
```

You do not need to manually clean up background processes or edit state files.

## State Layout

State layout is for debugging only:

- `MERIDIAN_STATE_ROOT/spawns.jsonl`: spawn events
- `MERIDIAN_STATE_ROOT/spawns/<id>/`: per-spawn artifacts and logs
- `MERIDIAN_FS_DIR`: shared filesystem between spawns

Prefer CLI reads and environment variables over hardcoded `.meridian/...` paths.

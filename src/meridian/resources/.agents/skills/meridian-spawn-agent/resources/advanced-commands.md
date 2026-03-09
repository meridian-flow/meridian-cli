# Advanced Spawn Commands

Read this when you need continue, cancel, stats, debugging, or model selection — commands outside the core spawn → wait → show loop.

## Continue & Fork

Resume a previous spawn's harness session, or fork it to try an alternate approach:

```bash
meridian spawn --continue SPAWN_ID -p "Follow up instruction"
meridian spawn --continue SPAWN_ID --fork -p "Try alternate approach"
```

`--continue` reuses the harness session (conversation history preserved). `--fork` branches from the same session but creates a new spawn ID.

## Cancel

```bash
meridian spawn cancel SPAWN_ID
```

Sends SIGINT to the harness process. The spawn finalizes with exit code 130.

## Stats

```bash
meridian spawn stats
meridian spawn stats --session ID
```

Aggregate cost, token, and duration stats across spawns. Use `--session` to scope to a specific coordination session.

## Spawn Show Flags

```bash
meridian spawn show SPAWN_ID --no-report     # omit the full report text
meridian spawn show SPAWN_ID --include-files  # include file metadata
```

## Debugging & Logs

Each spawn writes a stderr log to `.meridian/spawns/<spawn-id>/stderr.log` — the full harness session trace with every tool call and reasoning step.

```bash
# Get the log path from spawn metadata
meridian spawn show SPAWN_ID
# → look for "log_path" in the JSON output

# Tail a running spawn's log
tail -f ".meridian/spawns/SPAWN_ID/stderr.log"
```

## Model Selection

```bash
meridian models list          # discover available models
meridian models show MODEL    # inspect model metadata and harness routing
```

The CLI routes each model to the correct harness automatically — you don't need to specify a harness.

## Shared Filesystem

Spawns can exchange data through `$MERIDIAN_FS_DIR` (defaults to `.meridian/fs/`):

```bash
mkdir -p "$MERIDIAN_FS_DIR"
echo "result" > "$MERIDIAN_FS_DIR/step-a-output.txt"
cat "$MERIDIAN_FS_DIR/step-b-output.txt"
```

Meridian provides the directory — agents organize it however they want.

## Permission Tiers

Override tool access with `--permission`:

```bash
meridian spawn -m MODEL -p "Read-only analysis" --permission read-only
```

Tiers: `read-only`, `workspace-write`, `full-access`.

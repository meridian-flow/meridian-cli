# Agent CLI Spec (Target)

This document defines the target CLI surface for agent mode.

Agent mode is enabled when `MERIDIAN_DEPTH` is greater than `0`.

## Root Help

```text
Usage: meridian COMMAND [ARGS]

Commands:
  spawn: Spawn and manage subagents
  models: Model catalog commands
  skills: Skills catalog commands
```

No global parameters are shown in agent root help.

## Output Behavior

- Default output format is JSON in agent mode.
- No extra flags required for JSON output.

## Spawn Command Behavior

- Primary action: `meridian spawn -m MODEL -p "PROMPT"`.
- Management commands: `meridian spawn list|show|wait|continue|stats`.
- Default action with no spawn subcommand: create a new spawn.

## State Root Rule

Spawn operations use the repo's shared `.meridian/` state root and shared
filesystem at `MERIDIAN_FS_DIR`.

## Visibility Rules

- Hidden from agent root help: `doctor`, `completion`, `config`, `init`, `serve`, `sync`.
- Removed entirely: `grep`.

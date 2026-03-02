# Human CLI Spec (Target)

This document defines the target CLI surface for human mode.

Human mode is used when `MERIDIAN_SPACE_ID` is not set.

## Root Help

```text
Usage: meridian COMMAND [ARGS]

Commands:
  start: Launch a primary agent session
  spawn: Spawn and manage subagents
  models: Model catalog
  skills: Skills catalog
  config: Configuration
  init: Initialize project
  doctor: Spawn diagnostics
  completion: Shell completion
```

## Global Parameters

```text
--format: Output format: text (default), json, porcelain
--config: Path to config overlay
```

Legacy compatibility flags (`--json`, `--porcelain`, `--yes`, `--no-input`) may still be accepted during transition, but are hidden from help.

## Spawn Command Behavior

- Primary action: `meridian spawn -m MODEL -p "PROMPT"`.
- Management commands: `meridian spawn list|show|wait|continue|stats`.
- Default action with no spawn subcommand: create a new spawn.

## Space Scoping Rule

Spawn operations require explicit space context:

- set `MERIDIAN_SPACE_ID`, or
- pass `--space`.

No auto-create fallback.


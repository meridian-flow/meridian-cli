---
name: __meridian-session-context
description: Session context mining via meridian CLI. Reading transcripts, searching decisions, and discovering sessions per work item. Use when you need historical context from parent sessions, prior spawns, or related work items.
---

# Session Context

Use `meridian` session commands to mine historical context quickly.

## Parent Session Inheritance

`$MERIDIAN_CHAT_ID` is inherited from the spawning session. `meridian session log` and
`meridian session search` therefore read the parent's transcript, not your own (spawns
usually start with no meaningful prior history). This is the primary way to recover
decision context from the conversation that launched you.

## Reading Conversations

`meridian session log <ref>` reads a session transcript.

Supported refs:
- chat id (`c123`)
- spawn id (`p123`)
- harness session id

Key flags:
- `--last N` / `-n N` - show last `N` messages (default `5`; `-n 0` for all)
- `-c N` - compaction segment (`0` = latest, `1` = previous, etc.)
- `--offset N` - skip `N` messages from end (for paging forward)

```bash
# Read last 10 messages from parent session
meridian session log $MERIDIAN_CHAT_ID --last 10

# Walk compaction segments for full history
meridian session log $MERIDIAN_CHAT_ID -c 0
meridian session log $MERIDIAN_CHAT_ID -c 1
meridian session log $MERIDIAN_CHAT_ID -c 2

# Page through a long segment
meridian session log $MERIDIAN_CHAT_ID --last 20 --offset 20
```

## Searching for Decisions

`meridian session search <query> <ref>` runs case-insensitive text search across all
compaction segments. Results include matching messages, content previews, and navigation
commands to jump to surrounding context.

```bash
# Find where a decision was made
meridian session search "decided" $MERIDIAN_CHAT_ID

# Search a specific spawn's session
meridian session search "error" p107
```

Each match includes a Navigate command you can run to inspect nearby messages.

## Discovering Sessions per Work Item

`meridian work sessions <work_id>` lists sessions that have touched a work item.
Use `--all` to include historical sessions.

```bash
# Which sessions touched this work item?
meridian work sessions auth-refactor

# Include completed/archived sessions
meridian work sessions auth-refactor --all
```

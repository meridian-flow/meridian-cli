# Spawn Children Command — Implementation Plan

## Problem

When an orchestrator spawns p730 and p730 spawns children (p731, p732...), there's no way to discover those children without grepping raw JSONL. `meridian session log` works fine if you have the ID, but you can't get the ID.

## Changes

### 1. Add `parent_id` to spawn store (spawn_store.py)

- Add `parent_id: str | None = None` to `SpawnRecord` (line 66 area)
- Add `parent_id: str | None = None` to `SpawnStartEvent` (line 98 area)
- Add `parent_id` to `_record_from_events` SpawnStartEvent handler (line 401 area)
- Add `parent_id` to `_empty_record` if it exists

### 2. Pass parent_id through spawn creation (execute.py)

- In `_init_spawn()` (line 227), pass `parent_id=str(resolved_context.spawn_id)` to `start_spawn()`
- Add `parent_id` parameter to `start_spawn()` function signature

### 3. Add `spawn children <id>` CLI command (spawn.py)

- New command that calls `list_spawns(state_root, filters={"parent_id": spawn_id})`
- Output format: same as `spawn list` but filtered to children
- Recursive `--tree` flag optional (can defer)

### 4. Add `spawn show` parent/children display

- When showing a spawn, include `parent_id` if present
- Include count of children

## Files to modify

1. `src/meridian/lib/state/spawn_store.py` — SpawnRecord, SpawnStartEvent, _record_from_events, start_spawn
2. `src/meridian/lib/ops/spawn/execute.py` — _init_spawn passes parent_id
3. `src/meridian/cli/spawn.py` — new children subcommand

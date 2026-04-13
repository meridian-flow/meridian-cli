# Spec: Skill Directory Conflict Handling (R4)

## Conflict Resolution Strategy

### SKILL-01: Skill conflicts use overwrite, not merge
When a conflict (both source and local changed) is detected for an item with `ItemKind::Skill`,
the system shall plan `PlannedAction::Overwrite` (source wins), not `PlannedAction::Merge`.

**Rationale:** Skills are directories containing `SKILL.md` + optional `resources/`. Three-way merge operates on byte streams and cannot meaningfully merge directory trees. Since there are no real users, force-overwrite is the simplest correct option. This matches `--force` behavior but applies specifically to skill conflicts regardless of the `--force` flag.

### SKILL-02: Skill conflicts warn the user
When a skill conflict is resolved by overwriting,
the system shall emit a warning indicating the skill name and that local modifications were overwritten.

### SKILL-03: Agent conflicts still merge
When a conflict is detected for an item with `ItemKind::Agent`,
the system shall continue to plan `PlannedAction::Merge` (three-way merge) as before.
The `--force` flag still overrides to `PlannedAction::Overwrite` for agents.

### SKILL-04: Planner branches on ItemKind for conflicts
When planning conflict resolution for copy-materialized items,
the planner shall check `target.id.kind` and branch:
- `ItemKind::Agent` → existing merge logic
- `ItemKind::Skill` → overwrite (source wins)

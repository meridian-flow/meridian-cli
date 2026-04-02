# F15: Fix Collision Rename for Cross-Package Dependencies

## Problem

`src/sync/target.rs:319-327` in `rewrite_skill_refs()`:

```rust
let selected = entries
    .iter()
    .find(|(_, source)| source == &source_name)
    .or_else(|| entries.first());
```

When an agent from source A references a collision-renamed skill, this code:
1. First tries to find the renamed version from the agent's own source (correct).
2. Falls back to `entries.first()` — arbitrary HashMap iteration order (incorrect).

For cross-package deps (agent source A, skill from dependency source B), neither condition works correctly. The agent's source doesn't appear in the rename entries (it didn't produce the skill), so it falls through to `entries.first()` which may pick source C's version.

The `_graph` parameter is already passed to `rewrite_skill_refs()` but unused.

## Design

### Algorithm

For each agent that references a renamed skill, determine the correct renamed version using this priority:

1. **Same-source match:** If the agent's source also produced a renamed version of this skill, use it. (Existing behavior, correct.)
2. **Dependency match:** Walk the agent's source's declared dependencies (from `graph.nodes[agent_source].deps`). If a dependency source produced a renamed version of this skill, use it. This is the cross-package case.
3. **No match:** If neither same-source nor dependency match, skip the rewrite for this skill reference. This is safer than the current `entries.first()` which picks arbitrarily.

### Implementation

In `rewrite_skill_refs()`, replace:
```rust
let selected = entries
    .iter()
    .find(|(_, source)| source == &source_name)
    .or_else(|| entries.first());
```

With:
```rust
let agent_deps: &[SourceName] = graph.nodes.get(&source_name)
    .map(|n| n.deps.as_slice())
    .unwrap_or(&[]);

let selected = entries
    .iter()
    .find(|(_, source)| source == &source_name)
    .or_else(|| entries.iter().find(|(_, source)| agent_deps.contains(source)));
```

### Rename parameter

Change `_graph` to `graph` (remove the underscore prefix).

### Edge Cases

**No manifest, no declared deps:** `graph.nodes[source].deps` is empty. The fallback finds nothing, and the skill reference is left unchanged. This is correct — without dependency information, we can't determine which renamed skill the agent intended. The agent keeps its original reference, and `mars doctor` will flag the broken reference post-sync.

**Multiple deps provide the same renamed skill:** The first matching dep in `deps` order wins. Since `deps` comes from manifest declaration order (stable, author-controlled), this is deterministic and matches author intent.

**Agent from a source not in the graph:** `graph.nodes.get(&source_name)` returns `None`, `deps` defaults to `&[]`. Falls through to no match — safe.

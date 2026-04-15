# Dead Code Cleanup

Three pieces of dead or misleading code to remove.

## 1. `check_collisions()` — Lines 117-157 of target.rs

Entirely dead. The function body acknowledges it doesn't work (`"Let's just return empty for now"`). Superseded by `build_with_collisions()` which integrates collision detection into the build phase. No callers in production or test code.

**Action:** Delete the function.

## 2. `build()` — Lines 51-111 of target.rs

Used by 8 tests but not production code. Production path goes through `build_with_collisions()`. Having both means tests exercise a different code path than what runs in production.

**Action:** Delete `build()`. Migrate all 8 test call sites to `build_with_collisions()`:

| Test | Current call | Migration |
|---|---|---|
| `build_single_source_no_filter` (line 789) | `build(&graph, &config)` | `build_with_collisions(&graph, &config)` → use `.0` for target |
| unnamed rename test (line 814) | `build(&graph, &config)` | Same |
| `build_with_agents_filter` (line 1015) | `build(&graph, &config)` | Same |
| `build_with_exclude_filter` (line 1034) | `build(&graph, &config)` | Same |
| `build_target_items_have_correct_hashes` (line 1046) | `build(&graph, &config)` | Same |
| `unmanaged_disk_path_collision_errors` (line 1062) | `build(&graph, &config)` | Same |
| `unmanaged_collision_skipped_when_hash_matches` (line 1087) | `build(&graph, &config)` | Same |
| `unmanaged_collision_still_errors_on_different_content` (line 1109) | `build(&graph, &config)` | Same |

The migration is mechanical: `build(g, c)` → `build_with_collisions(g, c).unwrap().0`. These tests use single sources, so no collisions — the `.1` (rename actions) will be empty, which is fine.

**Test isolation preserved:** Each test creates its own `TempDir` source tree. Using `build_with_collisions()` doesn't change what they test — they still test filtering, renaming, and basic target construction. They now also exercise the collision-detection code path (which finds no collisions, confirming the single-source happy path).

## 3. `DepSpec.items` — manifest/mod.rs line 36

Field exists in the schema, parses and round-trips correctly (tested), but has zero runtime effect. The resolver ignores it entirely. Users who set `items = ["coder", "reviewer"]` think they're scoping a dependency; they're not.

**Action:** Remove the field. Remove the test assertion that exercises it (`parse_valid_manifest_with_deps` test, lines 91-92). Keep the test itself — just remove the `items` line from the test TOML and the assertion.

The `items` field can be re-added when items-level dependency filtering is implemented. Removing dead schema is better than shipping a false API promise.

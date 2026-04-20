"""Public state-layer API surface.

This package-level export list is intentionally narrow: external callers should
import only these names, while internal state modules remain private unless
explicitly promoted here.
"""

# Lifecycle service boundary is public; transition writes behind it stay in spawn_store.
from meridian.lib.core.lifecycle import LifecycleEvent, LifecycleHook, SpawnLifecycleService
from meridian.lib.state.artifact_store import (
    ArtifactStore,
    InMemoryStore,
    LocalStore,
    make_artifact_key,
)
from meridian.lib.state.paths import (
    StatePaths,
    StateRootPaths,
    ensure_gitignore,
    resolve_fs_dir,
    resolve_spawn_log_dir,
    resolve_state_paths,
    resolve_work_scratch_dir,
    spawn_log_subpath,
)
from meridian.lib.state.spawn_store import (
    SpawnRecord,
    finalize_spawn,
    get_spawn,
    list_spawns,
    next_spawn_id,
    spawn_stats,
    start_spawn,
)

# Transitional compatibility exports: keep direct lifecycle writers public only
# until R13b privatization lands. New executor-facing code should use
# SpawnLifecycleService as the authoritative lifecycle seam.
__all__ = [
    "ArtifactStore",
    "InMemoryStore",
    "LifecycleEvent",
    "LifecycleHook",
    "LocalStore",
    "SpawnLifecycleService",
    "SpawnRecord",
    "StatePaths",
    "StateRootPaths",
    "ensure_gitignore",
    "finalize_spawn",
    "get_spawn",
    "list_spawns",
    "make_artifact_key",
    "next_spawn_id",
    "resolve_fs_dir",
    "resolve_spawn_log_dir",
    "resolve_state_paths",
    "resolve_work_scratch_dir",
    "spawn_log_subpath",
    "spawn_stats",
    "start_spawn",
]

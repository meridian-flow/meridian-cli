
from meridian.lib.state.paths import (
    SpacePaths,
    ensure_gitignore,
    resolve_fs_dir,
    resolve_state_paths,
)


def test_space_path_resolvers_and_dataclass_fields(tmp_path):
    state_root = resolve_state_paths(tmp_path).root_dir
    paths = SpacePaths.from_space_dir(state_root)

    assert state_root == tmp_path / ".meridian"
    assert paths.spawns_jsonl == state_root / "spawns.jsonl"
    assert paths.spawns_lock == state_root / "spawns.lock"
    assert paths.sessions_jsonl == state_root / "sessions.jsonl"
    assert paths.sessions_lock == state_root / "sessions.lock"
    assert paths.sessions_dir == state_root / "sessions"
    assert paths.fs_dir == state_root / "fs"
    assert paths.spawns_dir == state_root / "spawns"
    assert resolve_fs_dir(tmp_path) == state_root / "fs"


def test_ensure_gitignore_seeds_on_first_init(tmp_path):
    gitignore = ensure_gitignore(tmp_path)

    assert gitignore == tmp_path / ".meridian" / ".gitignore"
    content = gitignore.read_text(encoding="utf-8")
    assert "!fs/**" in content
    assert "!work/**" in content


def test_ensure_gitignore_does_not_overwrite_user_edits(tmp_path):
    path = tmp_path / ".meridian" / ".gitignore"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("custom user content\n", encoding="utf-8")

    ensure_gitignore(tmp_path)

    assert path.read_text(encoding="utf-8") == "custom user content\n"


def test_resolve_state_paths_includes_sync_paths(tmp_path):
    paths = resolve_state_paths(tmp_path)

    assert paths.root_dir == tmp_path / ".meridian"
    assert paths.sync_lock_path == tmp_path / ".meridian" / "sync.lock"
    assert paths.sync_cache_dir == tmp_path / ".meridian" / "cache" / "sync"

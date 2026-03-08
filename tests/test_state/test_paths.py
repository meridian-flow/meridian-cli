
from meridian.lib.state.paths import (
    SpacePaths,
    ensure_gitignore,
    resolve_all_spaces_dir,
    resolve_space_dir,
    resolve_state_paths,
)


def test_space_path_resolvers_and_dataclass_fields(tmp_path):
    all_spaces = resolve_all_spaces_dir(tmp_path)
    space_dir = resolve_space_dir(tmp_path, "s12")
    paths = SpacePaths.from_space_dir(space_dir)

    assert all_spaces == tmp_path / ".meridian" / ".spaces"
    assert space_dir == tmp_path / ".meridian" / ".spaces" / "s12"
    assert paths.space_json == space_dir / "space.json"
    assert paths.space_lock == space_dir / "space.lock"
    assert paths.spawns_jsonl == space_dir / "spawns.jsonl"
    assert paths.spawns_lock == space_dir / "spawns.lock"
    assert paths.sessions_jsonl == space_dir / "sessions.jsonl"
    assert paths.sessions_lock == space_dir / "sessions.lock"
    assert paths.sessions_dir == space_dir / "sessions"
    assert paths.fs_dir == space_dir / "fs"
    assert paths.spawns_dir == space_dir / "spawns"


def test_ensure_gitignore_seeds_on_first_init(tmp_path):
    gitignore = ensure_gitignore(tmp_path)

    assert gitignore == tmp_path / ".meridian" / ".gitignore"
    content = gitignore.read_text(encoding="utf-8")
    assert "!.spaces/*/designs/**" in content
    assert "!.spaces/*/fs/**" in content
    assert "!sync.lock" in content


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

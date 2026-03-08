
import json

from meridian.lib.state.space_store import create_space, get_space, list_spaces


def test_create_space_writes_space_json_and_fs_and_gitignore(tmp_path):
    record = create_space(tmp_path, name="feature-auth")

    space_dir = tmp_path / ".meridian" / ".spaces" / record.id
    assert record.id == "s1"
    assert record.name == "feature-auth"
    assert (space_dir / "fs").is_dir()
    assert (tmp_path / ".meridian" / ".gitignore").exists()

    payload = json.loads((space_dir / "space.json").read_text(encoding="utf-8"))
    assert payload == {
        "schema_version": 1,
        "id": "s1",
        "name": "feature-auth",
        "created_at": record.created_at,
    }


def test_get_space_returns_none_when_missing(tmp_path):
    assert get_space(tmp_path, "s404") is None


def test_list_spaces_reads_all_space_json_files(tmp_path):
    create_space(tmp_path, name="one")
    create_space(tmp_path, name="two")

    spaces = list_spaces(tmp_path)
    assert [space.id for space in spaces] == ["s1", "s2"]
    assert [space.name for space in spaces] == ["one", "two"]

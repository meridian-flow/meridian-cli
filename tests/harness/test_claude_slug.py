from pathlib import Path

from meridian.lib.harness.claude import project_slug


def test_project_slug_normalizes_simple_dotted_and_special_paths() -> None:
    assert project_slug(Path("/home/user/project")) == "-home-user-project"
    assert (
        project_slug(Path("/home/user/.meridian/spawns/p1")) == "-home-user--meridian-spawns-p1"
    )
    assert (
        project_slug(Path("/tmp/meridian channel/@v1:child")) == "-tmp-meridian-channel--v1-child"
    )

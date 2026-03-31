from pathlib import Path

from meridian.lib.harness.claude import project_slug


def test_project_slug_encodes_simple_path() -> None:
    assert project_slug(Path("/home/user/project")) == "-home-user-project"


def test_project_slug_replaces_dots_with_dashes() -> None:
    assert (
        project_slug(Path("/home/user/.meridian/spawns/p1"))
        == "-home-user--meridian-spawns-p1"
    )


def test_project_slug_replaces_all_non_alphanumeric_characters() -> None:
    assert (
        project_slug(Path("/tmp/meridian channel/@v1:child"))
        == "-tmp-meridian-channel--v1-child"
    )

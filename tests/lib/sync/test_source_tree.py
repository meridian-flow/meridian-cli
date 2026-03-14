from pathlib import Path

from meridian.lib.sync.source_tree import discover_source_items


def test_discover_source_items_uses_conventional_layout(tmp_path: Path) -> None:
    tree = tmp_path / "source"
    (tree / "agents").mkdir(parents=True)
    (tree / "skills" / "dev-workflow").mkdir(parents=True)
    (tree / "agents" / "__meridian-orchestrator.md").write_text("# orchestrator\n", encoding="utf-8")
    (tree / "skills" / "dev-workflow" / "SKILL.md").write_text("# workflow\n", encoding="utf-8")

    items = discover_source_items(tree)

    assert [item.item_id for item in items] == [
        "agent:__meridian-orchestrator",
        "skill:dev-workflow",
    ]
    assert items[0].path == "agents/__meridian-orchestrator.md"
    assert items[1].path == "skills/dev-workflow/SKILL.md"


def test_discover_source_items_ignores_nonconforming_files(tmp_path: Path) -> None:
    tree = tmp_path / "source"
    (tree / "agents").mkdir(parents=True)
    (tree / "skills" / "bad-skill").mkdir(parents=True)
    (tree / "agents" / "notes.txt").write_text("ignore me\n", encoding="utf-8")
    (tree / "skills" / "bad-skill" / "README.md").write_text("ignore me\n", encoding="utf-8")

    assert discover_source_items(tree) == ()

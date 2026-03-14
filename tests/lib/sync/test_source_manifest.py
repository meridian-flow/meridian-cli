from pathlib import Path

import pytest

from meridian.lib.sync.source_manifest import ExportedSourceManifest, load_source_manifest


def test_load_source_manifest_parses_items_and_validates_paths(tmp_path: Path) -> None:
    tree = tmp_path / "source"
    (tree / "agents").mkdir(parents=True)
    (tree / "skills" / "dev-workflow").mkdir(parents=True)
    (tree / "agents" / "__meridian-orchestrator.md").write_text("# orchestrator\n", encoding="utf-8")
    (tree / "skills" / "dev-workflow" / "SKILL.md").write_text("# workflow\n", encoding="utf-8")
    (tree / "meridian-source.toml").write_text(
        """
[[items]]
kind = "agent"
name = "__meridian-orchestrator"
path = "agents/__meridian-orchestrator.md"
managed = true
system = true
depends_on = [{ kind = "skill", name = "dev-workflow" }]

[[items]]
kind = "skill"
name = "dev-workflow"
path = "skills/dev-workflow/SKILL.md"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    manifest = load_source_manifest(tree)

    assert manifest == ExportedSourceManifest(
        items=(
            manifest.items[0],
            manifest.items[1],
        )
    )
    assert manifest.items[0].item_id == "agent:__meridian-orchestrator"
    assert manifest.items[0].depends_on[0].item_id == "skill:dev-workflow"


def test_load_source_manifest_requires_exported_paths_to_exist(tmp_path: Path) -> None:
    tree = tmp_path / "source"
    tree.mkdir(parents=True)
    (tree / "meridian-source.toml").write_text(
        """
[[items]]
kind = "agent"
name = "__meridian-orchestrator"
path = "agents/__meridian-orchestrator.md"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(FileNotFoundError, match="Exported item path not found"):
        load_source_manifest(tree)

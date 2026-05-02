from pathlib import Path

from meridian.lib.catalog.skill import SkillRegistry, discover_skill_files
from tests.support.fixtures import write_skill


def test_discover_skill_files_indexes_only_immediate_skill_roots(tmp_path: Path) -> None:
    base = write_skill(tmp_path, "root", body="Base body")
    variant = tmp_path / ".mars" / "skills" / "root" / "variants" / "claude" / "SKILL.md"
    variant.parent.mkdir(parents=True)
    variant.write_text("# Variant body", encoding="utf-8")

    assert discover_skill_files(tmp_path / ".mars" / "skills") == [base]


def test_skill_registry_ignores_nested_variant_documents_for_listing(tmp_path: Path) -> None:
    write_skill(tmp_path, "root", body="Base body")
    variant = tmp_path / ".mars" / "skills" / "root" / "variants" / "claude" / "SKILL.md"
    variant.parent.mkdir(parents=True)
    variant.write_text(
        "---\nname: nested-variant\ndescription: should not list\n---\n\nVariant body",
        encoding="utf-8",
    )

    registry = SkillRegistry(project_root=tmp_path)

    assert [item.name for item in registry.list_skills()] == ["root"]

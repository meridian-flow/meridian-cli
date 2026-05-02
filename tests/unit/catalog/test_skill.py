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


def test_skill_registry_load_selects_model_token_variant_first(tmp_path: Path) -> None:
    base_path = write_skill(tmp_path, "root", body="Base body", description="Base description")
    skill_root = tmp_path / ".mars" / "skills" / "root"
    (skill_root / "variants" / "codex" / "gpt-5.5").mkdir(parents=True)
    token_variant = skill_root / "variants" / "codex" / "gpt-5.5" / "SKILL.md"
    token_variant.write_text(
        "---\nname: ignored\ndescription: ignored\n---\n\nToken variant body",
        encoding="utf-8",
    )
    (skill_root / "variants" / "codex" / "openai-gpt-5.5").mkdir(parents=True)
    canonical_variant = skill_root / "variants" / "codex" / "openai-gpt-5.5" / "SKILL.md"
    canonical_variant.write_text("Canonical variant body", encoding="utf-8")
    (skill_root / "variants" / "codex").mkdir(exist_ok=True)
    harness_variant = skill_root / "variants" / "codex" / "SKILL.md"
    harness_variant.write_text("Harness variant body", encoding="utf-8")

    loaded = SkillRegistry(project_root=tmp_path).load(
        ["root"],
        harness_id="codex",
        selected_model_token="gpt-5.5",
        canonical_model_id="openai-gpt-5.5",
    )[0]

    assert loaded.name == "root"
    assert loaded.description == "Base description"
    assert loaded.content == base_path.read_text(encoding="utf-8").replace(
        "Base body\n", "Token variant body"
    )
    assert "name: root" in loaded.content
    assert "description: Base description" in loaded.content
    assert "name: ignored" not in loaded.content
    assert loaded.path == token_variant.resolve().as_posix()


def test_skill_registry_load_falls_back_through_canonical_harness_and_base(
    tmp_path: Path,
) -> None:
    base_path = write_skill(tmp_path, "root", body="Base body")
    skill_root = tmp_path / ".mars" / "skills" / "root"
    canonical_variant = skill_root / "variants" / "codex" / "openai-gpt-5.5" / "SKILL.md"
    canonical_variant.parent.mkdir(parents=True)
    canonical_variant.write_text("Canonical variant body", encoding="utf-8")
    harness_variant = skill_root / "variants" / "codex" / "SKILL.md"
    harness_variant.write_text("Harness variant body", encoding="utf-8")

    registry = SkillRegistry(project_root=tmp_path)

    base_content = base_path.read_text(encoding="utf-8")
    assert registry.load(
        ["root"],
        harness_id="codex",
        selected_model_token="gpt-5.4",
        canonical_model_id="openai-gpt-5.5",
    )[0].content == base_content.replace("Base body\n", "Canonical variant body")
    assert registry.load(
        ["root"],
        harness_id="codex",
        selected_model_token="gpt-5.4",
        canonical_model_id="openai-gpt-5.4",
    )[0].content == base_content.replace("Base body\n", "Harness variant body")
    assert registry.load(
        ["root"],
        harness_id="claude",
        selected_model_token="gpt-5.4",
        canonical_model_id="openai-gpt-5.4",
    )[0].content == base_content


def test_skill_registry_load_uses_exact_model_matching_only(tmp_path: Path) -> None:
    base_path = write_skill(tmp_path, "root", body="Base body")
    variant = tmp_path / ".mars" / "skills" / "root" / "variants" / "codex" / "gpt" / "SKILL.md"
    variant.parent.mkdir(parents=True)
    variant.write_text("Prefix variant body", encoding="utf-8")

    loaded = SkillRegistry(project_root=tmp_path).load(
        ["root"],
        harness_id="codex",
        selected_model_token="gpt-5.5",
        canonical_model_id="openai-gpt-5.5",
    )[0]

    assert loaded.content == base_path.read_text(encoding="utf-8")

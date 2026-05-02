from pathlib import Path

from meridian.lib.catalog.bootstrap import BootstrapRegistry


def test_bootstrap_registry_loads_two_tiers_in_deterministic_order(tmp_path: Path) -> None:
    skill_b = tmp_path / ".mars" / "skills" / "z-skill" / "resources"
    skill_a = tmp_path / ".mars" / "skills" / "a-skill" / "resources"
    pkg_b = tmp_path / ".mars" / "bootstrap" / "z-doc"
    pkg_a = tmp_path / ".mars" / "bootstrap" / "a-skill"
    for path in (skill_b, skill_a, pkg_b, pkg_a):
        path.mkdir(parents=True)
    (skill_b / "BOOTSTRAP.md").write_text("skill z", encoding="utf-8")
    (skill_a / "BOOTSTRAP.md").write_text("skill a", encoding="utf-8")
    (pkg_b / "BOOTSTRAP.md").write_text("pkg z", encoding="utf-8")
    (pkg_a / "BOOTSTRAP.md").write_text("pkg same name", encoding="utf-8")

    docs = BootstrapRegistry(tmp_path / ".mars").load_all()

    assert [(doc.kind, doc.logical_name) for doc in docs] == [
        ("bootstrap", "a-skill"),
        ("bootstrap", "z-skill"),
        ("bootstrap", "a-skill"),
        ("bootstrap", "z-doc"),
    ]
    assert docs[0].content == "# Bootstrap: a-skill\n\nskill a"
    assert docs[2].content == "# Bootstrap: a-skill (package)\n\npkg same name"

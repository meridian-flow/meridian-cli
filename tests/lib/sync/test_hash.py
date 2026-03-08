import hashlib
from pathlib import Path

import frontmatter  # type: ignore[import-untyped]
import pytest

from meridian.lib.sync.hash import (
    compute_file_body_hash,
    compute_item_hash,
    compute_tree_hash,
)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _format_hash(data: bytes) -> str:
    return f"sha256:{_sha256_hex(data)}"


def _expected_tree_hash(directory: Path, *, entry_point: str = "SKILL.md") -> str:
    entries: list[tuple[str, str]] = []
    for path in sorted(candidate for candidate in directory.rglob("*") if candidate.is_file()):
        relative_path = path.relative_to(directory).as_posix()
        if relative_path.startswith(".git/"):
            continue
        if relative_path == entry_point:
            body = str(frontmatter.loads(path.read_text(encoding="utf-8")).content)
            digest = _sha256_hex(body.encode("utf-8"))
        else:
            digest = _sha256_hex(path.read_bytes())
        entries.append((relative_path, digest))

    manifest = "".join(f"{relative_path}\0{digest}\n" for relative_path, digest in entries)
    return _format_hash(manifest.encode("utf-8"))


def test_compute_file_body_hash_excludes_frontmatter(tmp_path: Path) -> None:
    agent_path = tmp_path / "agent.md"
    agent_path.write_text(
        "---\nname: custom-agent\nmodel: gpt\n---\nBody line 1\nBody line 2\n",
        encoding="utf-8",
    )

    expected = _format_hash(
        str(frontmatter.loads(agent_path.read_text(encoding="utf-8")).content).encode("utf-8")
    )

    assert compute_file_body_hash(agent_path) == expected

    agent_path.write_text(
        "---\nname: renamed-agent\nmodel: claude\nsandbox: workspace-write\n---\n"
        "Body line 1\nBody line 2\n",
        encoding="utf-8",
    )

    assert compute_file_body_hash(agent_path) == expected


def test_compute_file_body_hash_without_frontmatter(tmp_path: Path) -> None:
    agent_path = tmp_path / "agent.md"
    agent_path.write_text("# Agent\n\nPlain markdown body.\n", encoding="utf-8")

    expected = _format_hash(
        str(frontmatter.loads(agent_path.read_text(encoding="utf-8")).content).encode("utf-8")
    )

    assert compute_file_body_hash(agent_path) == expected


def test_compute_tree_hash_for_simple_skill_directory(tmp_path: Path) -> None:
    skill_dir = tmp_path / "simple-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: simple-skill\nmodel: local\n---\nCore skill instructions.\n",
        encoding="utf-8",
    )

    expected = _expected_tree_hash(skill_dir)

    assert compute_tree_hash(skill_dir) == expected


def test_compute_tree_hash_with_extra_files_uses_raw_bytes_for_non_entry_files(
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "skill"
    (skill_dir / "nested").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: sync-skill\nmodel: gpt\n---\nPrimary instructions.\n",
        encoding="utf-8",
    )
    (skill_dir / "README.md").write_text(
        "---\ntitle: supplemental\n---\nThis frontmatter stays part of the hash.\n",
        encoding="utf-8",
    )
    (skill_dir / "nested" / "template.txt").write_bytes(b"template-bytes-\x00-\xff")

    expected = _expected_tree_hash(skill_dir)

    assert compute_tree_hash(skill_dir) == expected


def test_compute_tree_hash_rejects_symlinks(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    target = skill_dir / "real.txt"
    target.write_text("real file\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("Body\n", encoding="utf-8")
    (skill_dir / "alias.txt").symlink_to(target)

    with pytest.raises(ValueError, match="alias.txt"):
        compute_tree_hash(skill_dir)


def test_compute_tree_hash_excludes_git_directory(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skill"
    (skill_dir / ".git").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: git-test\n---\nTracked body.\n",
        encoding="utf-8",
    )
    (skill_dir / ".git" / "config").write_text("[core]\n", encoding="utf-8")

    hash_with_git = compute_tree_hash(skill_dir)

    (skill_dir / ".git" / "config").write_text("[core]\nrepositoryformatversion = 1\n", encoding="utf-8")

    assert compute_tree_hash(skill_dir) == hash_with_git


def test_compute_tree_hash_is_deterministic_regardless_of_creation_order(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    (first / "docs").mkdir(parents=True)
    (first / "SKILL.md").write_text("---\nname: demo\n---\nShared body.\n", encoding="utf-8")
    (first / "docs" / "b.txt").write_text("B\n", encoding="utf-8")
    (first / "a.txt").write_text("A\n", encoding="utf-8")

    (second / "docs").mkdir(parents=True)
    (second / "a.txt").write_text("A\n", encoding="utf-8")
    (second / "docs" / "b.txt").write_text("B\n", encoding="utf-8")
    (second / "SKILL.md").write_text("---\nmodel: x\nname: demo\n---\nShared body.\n", encoding="utf-8")

    assert compute_tree_hash(first) == compute_tree_hash(second)


def test_compute_item_hash_dispatches_by_kind(tmp_path: Path) -> None:
    agent_path = tmp_path / "agent.md"
    agent_path.write_text("---\nname: agent\n---\nBody\n", encoding="utf-8")
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: skill\n---\nBody\n", encoding="utf-8")

    assert compute_item_hash(agent_path, "agent") == compute_file_body_hash(agent_path)
    assert compute_item_hash(skill_dir, "skill") == compute_tree_hash(skill_dir)

    with pytest.raises(ValueError, match="unknown"):
        compute_item_hash(agent_path, "unknown")

"""Behavioral tests for project path validation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from meridian.lib.app.path_security import (
    PathSecurityError,
    is_safe_relative_path,
    validate_project_path,
)


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    return project


@pytest.mark.parametrize(
    "relative_path",
    [
        "src/main.py",
        "./src/main.py",
        "src\\main.py",
        "src/../tests/test.py",
        "does/not/exist.txt",
    ],
)
def test_validate_project_path_accepts_paths_within_root(
    project_root: Path,
    relative_path: str,
) -> None:
    (project_root / "src").mkdir(exist_ok=True)
    (project_root / "tests").mkdir(exist_ok=True)

    resolved = validate_project_path(project_root, relative_path)
    assert resolved.is_relative_to(project_root.resolve())


@pytest.mark.parametrize(
    ("relative_path", "error_fragment"),
    [
        ("/etc/passwd", "Absolute paths not allowed"),
        ("C:\\Windows\\system32", "Windows absolute paths not allowed"),
        ("C:/Windows/system32", "Windows absolute paths not allowed"),
        ("\\\\server\\share\\file.txt", "UNC paths not allowed"),
        ("../secret.txt", "escapes project root"),
        ("src\\..\\..\\etc\\passwd", "escapes project root"),
    ],
)
def test_validate_project_path_rejects_escapes_and_absolute_forms(
    project_root: Path,
    relative_path: str,
    error_fragment: str,
) -> None:
    with pytest.raises(PathSecurityError, match=error_fragment):
        validate_project_path(project_root, relative_path)


@pytest.mark.parametrize(
    ("relative_path", "error_fragment"),
    [
        ("", "cannot be empty"),
        ("   ", "cannot be empty"),
        ("file\x00.txt", "null bytes"),
    ],
)
def test_validate_project_path_rejects_invalid_input(
    project_root: Path,
    relative_path: str,
    error_fragment: str,
) -> None:
    with pytest.raises(PathSecurityError, match=error_fragment):
        validate_project_path(project_root, relative_path)


def test_validate_project_path_requires_absolute_project_root() -> None:
    with pytest.raises(PathSecurityError, match="project_root must be absolute"):
        validate_project_path(Path("relative/root"), "file.txt")


def test_validate_project_path_single_dot_resolves_to_project_root(project_root: Path) -> None:
    assert validate_project_path(project_root, ".") == project_root.resolve()


def test_validate_project_path_allows_unicode_and_spaces_within_root(project_root: Path) -> None:
    target = project_root / "données" / "résumé.txt"
    target.parent.mkdir(parents=True)
    target.write_text("ok", encoding="utf-8")

    resolved = validate_project_path(project_root, "données/résumé.txt")
    assert resolved == target.resolve()


@pytest.mark.skipif(sys.platform == "win32", reason="Symlinks need admin on Windows")
def test_validate_project_path_allows_symlink_within_root(project_root: Path) -> None:
    target = project_root / "real" / "file.txt"
    target.parent.mkdir(parents=True)
    target.write_text("content")

    link = project_root / "link"
    link.symlink_to(target)

    assert validate_project_path(project_root, "link") == target.resolve()


@pytest.mark.skipif(sys.platform == "win32", reason="Symlinks need admin on Windows")
def test_validate_project_path_rejects_symlink_escape(project_root: Path, tmp_path: Path) -> None:
    escape_target = tmp_path / "secret.txt"
    escape_target.write_text("secret")

    escape_link = project_root / "escape"
    escape_link.symlink_to(escape_target)

    with pytest.raises(PathSecurityError, match="escapes project root"):
        validate_project_path(project_root, "escape")


@pytest.mark.parametrize(
    ("relative_path", "expected"),
    [
        ("src/main.py", True),
        ("src/../tests", True),
        ("../secret", False),
        ("/etc/passwd", False),
        ("C:\\Windows", False),
        ("\\\\server\\share", False),
        ("file\x00.txt", False),
    ],
)
def test_is_safe_relative_path_quick_check(relative_path: str, expected: bool) -> None:
    assert is_safe_relative_path(relative_path) is expected


def test_is_safe_relative_path_whitespace_only_is_not_authoritative(project_root: Path) -> None:
    assert is_safe_relative_path("   ") is True
    with pytest.raises(PathSecurityError, match="cannot be empty"):
        validate_project_path(project_root, "   ")

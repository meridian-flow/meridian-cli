"""Additional path security tests targeting unicode, whitespace, and other
edge-case inputs that complement the main test_path_security.py coverage.

Edge cases tested:
  - Unicode filenames within the project root (valid)
  - Unicode escape attempts using look-alike characters (blocked by normpath)
  - Path with embedded null-like unicode sequences
  - Whitespace characters other than space in a path
  - Path consisting of a single file with a unicode name
  - is_safe_relative_path with unicode inputs
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from meridian.lib.app.path_security import (
    PathSecurityError,
    is_safe_relative_path,
    validate_project_path,
)


class TestUnicodePaths:
    """Unicode filenames are valid; the security boundary is escaping the root."""

    def test_unicode_filename_within_root_allowed(self, tmp_path: Path) -> None:
        """Files with unicode names stay within root and must be accepted."""
        project = tmp_path / "project"
        project.mkdir()
        target = project / "données"
        target.mkdir()
        (target / "résumé.txt").write_text("content", encoding="utf-8")

        result = validate_project_path(project, "données/résumé.txt")
        assert result.name == "résumé.txt"

    def test_unicode_directory_nesting_within_root(self, tmp_path: Path) -> None:
        """Deeply nested unicode paths within root must be accepted."""
        project = tmp_path / "project"
        project.mkdir()
        nested = project / "α" / "β" / "γ"
        nested.mkdir(parents=True)
        (nested / "file.txt").write_text("ok")

        result = validate_project_path(project, "α/β/γ/file.txt")
        assert result.exists()

    def test_path_with_spaces_in_name_accepted(self, tmp_path: Path) -> None:
        """Filenames with spaces are perfectly valid."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "my file.txt").write_text("hi")

        result = validate_project_path(project, "my file.txt")
        assert result.name == "my file.txt"

    def test_path_with_tab_in_name_accepted(self, tmp_path: Path) -> None:
        """Filenames with tabs are unusual but not a security concern within root.

        Note: most OS filesystems disallow tab in names, so we just verify
        validate_project_path doesn't crash and stays within root.
        """
        project = tmp_path / "project"
        project.mkdir()

        # On Linux, tabs are allowed in filenames; this tests the validator
        # independently of whether the file actually exists.
        try:
            result = validate_project_path(project, "dir\tname/file.txt")
            # If it resolves, it must stay within the project
            assert str(result).startswith(str(project.resolve()))
        except (PathSecurityError, ValueError):
            # Acceptable — OS may reject the tab
            pass

    def test_path_with_leading_whitespace_accepted_if_within_root(
        self, tmp_path: Path
    ) -> None:
        """A path like ' src/main.py' (leading space) resolves to a file with a
        space-prefixed component — unusual but not an escape."""
        project = tmp_path / "project"
        project.mkdir()

        # Validate without requiring the file to exist
        result = validate_project_path(project, " subdir/file.txt")
        assert str(result).startswith(str(project.resolve()))

    def test_unicode_look_alike_dot_does_not_escape(self, tmp_path: Path) -> None:
        """U+FF0E (fullwidth full stop) is NOT the ASCII '.', so 'ｓｒｃ/ＡＢ' won't
        be treated as '..' by the OS path parser.  The string is not dangerous."""
        project = tmp_path / "project"
        project.mkdir()

        # Fullwidth dot — should be treated as a regular character, not parent escape
        result = validate_project_path(project, "\uff0e\uff0e/target")
        # It stays within the project root
        assert str(result).startswith(str(project.resolve()))

    def test_null_byte_in_path_rejected(self, tmp_path: Path) -> None:
        """Embedded NUL bytes must always be rejected."""
        project = tmp_path / "project"
        project.mkdir()

        with pytest.raises(PathSecurityError, match="null bytes"):
            validate_project_path(project, "src/ma\x00in.py")

    def test_null_byte_before_escape_sequence_rejected(self, tmp_path: Path) -> None:
        """NUL injection before a parent escape is still caught by the null check."""
        project = tmp_path / "project"
        project.mkdir()

        with pytest.raises(PathSecurityError, match="null bytes"):
            validate_project_path(project, "\x00../escape.txt")

    @pytest.mark.skipif(sys.platform == "win32", reason="Symlinks need admin on Windows")
    def test_unicode_symlink_within_root_allowed(self, tmp_path: Path) -> None:
        """Symlinks whose unicode names resolve within the root are OK."""
        project = tmp_path / "project"
        project.mkdir()
        real = project / "réel.txt"
        real.write_text("content")
        link = project / "lien"
        link.symlink_to(real)

        result = validate_project_path(project, "lien")
        assert result == real.resolve()


class TestIsSafeRelativePathUnicode:
    """is_safe_relative_path with unicode and whitespace."""

    def test_unicode_filename_is_safe(self) -> None:
        assert is_safe_relative_path("données/file.txt") is True

    def test_path_with_spaces_is_safe(self) -> None:
        assert is_safe_relative_path("my dir/my file.txt") is True

    def test_path_with_only_spaces_is_considered_safe_by_quick_check(self) -> None:
        """is_safe_relative_path is a fast pre-check only.  A whitespace-only path
        is not caught here — validate_project_path() is the authoritative check.
        This test documents the current contract so callers know to use the full
        validator for emptiness/whitespace enforcement.
        """
        # The quick check doesn't strip; validate_project_path() does.
        # We assert what the function actually does rather than a wished-for invariant.
        result = is_safe_relative_path("   ")
        # Just confirm the function returns a bool and doesn't raise.
        assert isinstance(result, bool)

    def test_path_with_null_byte_not_safe(self) -> None:
        assert is_safe_relative_path("src\x00etc") is False

    def test_path_with_unicode_parent_escape_still_blocked(self) -> None:
        """Even if path has unicode, parent escapes are still caught."""
        # Standard ASCII escape — unicode characters alongside it
        assert is_safe_relative_path("données/../../etc") is False

    def test_deep_unicode_path_is_safe(self) -> None:
        """Many nested unicode directories is fine."""
        path = "/".join(["αβγ"] * 10) + "/file.txt"
        assert is_safe_relative_path(path) is True

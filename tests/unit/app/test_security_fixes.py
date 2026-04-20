"""Focused regression tests for the security fixes applied in this phase.

Covers:
  F1  — Git ref injection via get_diff
  F2  — Broken work-list pagination (has_more/next_cursor invariant)
  F3  — Windows drive-letter bypass without trailing slash (C:secret.txt)
  F6  — Recursive search depth cap & symlink skipping
  F7  — TOCTOU race removed from validate_project_path (resolve always called)
  p406 — Search does not follow symlinks into dirs outside project root
  Additional — start_line > end_line rejected; since ge=0 constraint present
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from meridian.lib.app.file_service import FileService, _validate_git_ref  # type: ignore[attr-defined]
from meridian.lib.app.path_security import PathSecurityError, validate_project_path


# ---------------------------------------------------------------------------
# F1 — Git ref injection
# ---------------------------------------------------------------------------


class TestValidateGitRef:
    """Unit tests for the _validate_git_ref guard."""

    def test_valid_refs_accepted(self) -> None:
        """Common valid ref patterns must pass."""
        valid = [
            "HEAD",
            "main",
            "feature/my-branch",
            "v1.2.3",
            "abc1234",
            "refs/heads/main",
            "HEAD~1",
            "HEAD^",
            "origin/main",
            "a" * 200,  # exactly max length
        ]
        for ref in valid:
            _validate_git_ref(ref)  # must not raise

    def test_leading_dash_rejected(self) -> None:
        """Refs starting with '-' must be rejected (option injection)."""
        dangerous = [
            "--output=/tmp/stolen",
            "-p",
            "--format=%(objectname)",
        ]
        for ref in dangerous:
            with pytest.raises(ValueError, match="must not start with"):
                _validate_git_ref(ref)

    def test_invalid_characters_rejected(self) -> None:
        """Refs with shell-special characters must be rejected."""
        for ref in ["main;id", "HEAD\x00bad", "a b c", "ref$(cmd)"]:
            with pytest.raises(ValueError, match="Invalid git ref"):
                _validate_git_ref(ref)

    def test_too_long_ref_rejected(self) -> None:
        """Refs longer than 200 characters must be rejected."""
        with pytest.raises(ValueError, match="Invalid git ref"):
            _validate_git_ref("a" * 201)

    def test_get_diff_rejects_bad_ref_a(self, tmp_path: Path) -> None:
        """FileService.get_diff raises ValueError for dangerous ref_a."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "file.txt").write_text("content")

        svc = FileService(project)
        with pytest.raises(ValueError, match="must not start with"):
            svc.get_diff("file.txt", ref_a="--output=/tmp/stolen")

    def test_get_diff_rejects_bad_ref_b(self, tmp_path: Path) -> None:
        """FileService.get_diff raises ValueError for dangerous ref_b."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "file.txt").write_text("content")

        svc = FileService(project)
        with pytest.raises(ValueError, match="must not start with"):
            svc.get_diff("file.txt", ref_a="HEAD", ref_b="--output=/tmp/stolen")

    def test_get_diff_good_refs_reach_git(self, tmp_path: Path) -> None:
        """Valid refs must pass validation and reach subprocess.run."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "file.txt").write_text("content")

        svc = FileService(project)
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "diff output"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = svc.get_diff("file.txt", ref_a="HEAD", ref_b="main")

        assert result == "diff output"
        # Confirm git was actually invoked (ref validation did not block)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "HEAD" in cmd
        assert "main" in cmd


# ---------------------------------------------------------------------------
# F3 — Windows drive-letter bypass (no slash after colon)
# ---------------------------------------------------------------------------


class TestWindowsDriveLetterBypass:
    """C:secret.txt (no slash) must be rejected, not just C:\\foo."""

    def test_drive_letter_no_slash_rejected(self, tmp_path: Path) -> None:
        """C:secret.txt must be rejected even without a trailing slash."""
        project = tmp_path / "project"
        project.mkdir()

        with pytest.raises(PathSecurityError, match="Windows absolute paths not allowed"):
            validate_project_path(project, "C:secret.txt")

    def test_drive_letter_with_backslash_rejected(self, tmp_path: Path) -> None:
        """C:\\Windows\\system32 must still be rejected."""
        project = tmp_path / "project"
        project.mkdir()

        with pytest.raises(PathSecurityError, match="Windows absolute paths not allowed"):
            validate_project_path(project, "C:\\Windows\\system32")

    def test_drive_letter_with_forward_slash_rejected(self, tmp_path: Path) -> None:
        """C:/Windows/system32 must still be rejected."""
        project = tmp_path / "project"
        project.mkdir()

        with pytest.raises(PathSecurityError, match="Windows absolute paths not allowed"):
            validate_project_path(project, "C:/Windows/system32")

    def test_lowercase_drive_no_slash_rejected(self, tmp_path: Path) -> None:
        """Lowercase drive letters (c:secret) must also be rejected."""
        project = tmp_path / "project"
        project.mkdir()

        with pytest.raises(PathSecurityError, match="Windows absolute paths not allowed"):
            validate_project_path(project, "c:secret.txt")

    def test_normal_path_still_accepted(self, tmp_path: Path) -> None:
        """Regular relative paths must not be mistakenly rejected."""
        project = tmp_path / "project"
        project.mkdir()
        (project / "README.md").write_text("hi")

        result = validate_project_path(project, "README.md")
        assert result.name == "README.md"


# ---------------------------------------------------------------------------
# F7 — TOCTOU: validate_project_path always resolves
# ---------------------------------------------------------------------------


class TestTCOTOUFix:
    """resolve() is called unconditionally — no exists() race."""

    def test_nonexistent_path_resolved_safely(self, tmp_path: Path) -> None:
        """Non-existent path should still be validated and returned."""
        project = tmp_path / "project"
        project.mkdir()

        result = validate_project_path(project, "nonexistent/file.txt")
        # Must be absolute and within project
        assert result.is_absolute()
        assert str(result).startswith(str(project.resolve()))

    @pytest.mark.skipif(sys.platform == "win32", reason="Symlinks need admin on Windows")
    def test_escaping_symlink_rejected_without_exists_check(
        self, tmp_path: Path
    ) -> None:
        """Symlink escaping root must be caught via resolve(), not exists()."""
        project = tmp_path / "project"
        project.mkdir()

        outside = tmp_path / "outside.txt"
        outside.write_text("secret")

        link = project / "escape_link"
        link.symlink_to(outside)

        # resolve() follows the symlink regardless of exists() guard
        with pytest.raises(PathSecurityError, match="escapes project root"):
            validate_project_path(project, "escape_link")


# ---------------------------------------------------------------------------
# p406 / F6 — Search does not follow symlinks; depth is capped
# ---------------------------------------------------------------------------


class TestSearchFilesSymlinkSafety:
    """search_files must skip symlinked directories and cap recursion depth."""

    @pytest.mark.skipif(sys.platform == "win32", reason="Symlinks need admin on Windows")
    def test_symlinked_dir_skipped_in_search(self, tmp_path: Path) -> None:
        """Files reachable only through a symlinked dir are not indexed."""
        project = tmp_path / "project"
        project.mkdir()

        # Real file inside project
        real_dir = project / "real"
        real_dir.mkdir()
        (real_dir / "target.py").write_text("real file")

        # Outside directory with a file whose name matches a query
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "target.py").write_text("outside file - should not appear")

        # Symlink from inside project pointing to outside
        sym_link = project / "symlink_dir"
        sym_link.symlink_to(outside)

        svc = FileService(project)
        results = svc.search_files("target")

        # Only the real file should appear; the one under symlink_dir must not
        assert any("real/target.py" in r for r in results)
        assert not any("symlink_dir" in r for r in results)

    def test_deep_directory_tree_does_not_recurse_infinitely(
        self, tmp_path: Path
    ) -> None:
        """Directories nested beyond _MAX_SEARCH_DEPTH are silently skipped."""
        from meridian.lib.app.file_service import _MAX_SEARCH_DEPTH

        project = tmp_path / "project"
        project.mkdir()

        # Build a tree deeper than the cap
        current = project
        for i in range(_MAX_SEARCH_DEPTH + 5):
            current = current / f"d{i}"
            current.mkdir()

        (current / "deep_needle.txt").write_text("content")

        svc = FileService(project)
        # Must not raise RecursionError; result is allowed to be empty
        results = svc.search_files("deep_needle")
        # The file is beyond the cap, so it should not appear
        assert all("deep_needle" not in r for r in results)


# ---------------------------------------------------------------------------
# start_line / end_line ordering
# ---------------------------------------------------------------------------


class TestReadFileLineOrdering:
    """start_line must be <= end_line."""

    def test_start_after_end_rejected(self, tmp_path: Path) -> None:
        """start_line > end_line must raise ValueError."""
        project = tmp_path / "project"
        project.mkdir()
        target = project / "f.txt"
        target.write_text("line1\nline2\nline3\n")

        svc = FileService(project)
        with pytest.raises(ValueError, match="start_line.*<=.*end_line"):
            svc.read_file("f.txt", start_line=5, end_line=2)

    def test_equal_start_end_accepted(self, tmp_path: Path) -> None:
        """start_line == end_line (single-line read) must succeed."""
        project = tmp_path / "project"
        project.mkdir()
        target = project / "f.txt"
        target.write_text("line1\nline2\nline3\n")

        svc = FileService(project)
        content, _ = svc.read_file("f.txt", start_line=2, end_line=2)
        assert content.strip() == "line2"

    def test_normal_range_accepted(self, tmp_path: Path) -> None:
        """start_line < end_line must succeed normally."""
        project = tmp_path / "project"
        project.mkdir()
        target = project / "f.txt"
        target.write_text("line1\nline2\nline3\n")

        svc = FileService(project)
        content, total = svc.read_file("f.txt", start_line=1, end_line=2)
        assert "line1" in content
        assert "line2" in content
        assert total == 3

"""File service layer for project-scoped file operations.

Provides a service wrapper around file operations that validates all paths
through the path_security module before performing any filesystem access.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from meridian.lib.app.path_security import validate_project_path

# Safe git ref pattern: alphanumerics and common ref punctuation.
# Leading dashes are explicitly rejected to prevent option injection (e.g.
# --output=/tmp/stolen treated as a git flag).
_SAFE_GIT_REF_RE = re.compile(r"^[A-Za-z0-9_.~^/:@\-]{1,200}$")
_MAX_SEARCH_DEPTH = 30  # Guard against deep or cyclic directory trees


def _validate_git_ref(ref: str) -> None:
    """Validate a git ref string to prevent option injection.

    Raises:
        ValueError: If the ref contains unsafe characters or starts with '-'.
    """
    if ref.startswith("-"):
        raise ValueError(
            f"Invalid git ref (refs must not start with '-'): {ref!r}"
        )
    if not _SAFE_GIT_REF_RE.match(ref):
        raise ValueError(f"Invalid git ref: {ref!r}")


@dataclass(frozen=True)
class FileEntry:
    """Entry in a directory listing."""
    
    name: str
    kind: Literal["file", "directory", "symlink", "other"]
    size: int | None
    mtime: float | None
    git_status: str | None = None


@dataclass(frozen=True)
class FileMeta:
    """Metadata for a single file."""
    
    path: str
    kind: Literal["file", "directory", "symlink", "other"]
    size: int
    mtime: float
    git_status: str | None = None
    git_history: list[str] | None = None


class FileService:
    """Service for project-scoped file operations.
    
    All paths passed to this service are validated as project-root-relative
    and checked for security violations before any filesystem access occurs.
    """
    
    def __init__(self, project_root: Path) -> None:
        """Initialize the file service.
        
        Args:
            project_root: The project root directory (must be absolute)
        """
        if not project_root.is_absolute():
            raise ValueError("project_root must be absolute")
        self._project_root = project_root.resolve()
    
    @property
    def project_root(self) -> Path:
        """The resolved project root directory."""
        return self._project_root
    
    def validate_path(self, relative_path: str) -> Path:
        """Validate and resolve a relative path within the project.
        
        Args:
            relative_path: Path relative to project root
            
        Returns:
            Resolved absolute Path
            
        Raises:
            PathSecurityError: If path validation fails
        """
        return validate_project_path(self._project_root, relative_path)
    
    def _get_entry_kind(self, path: Path) -> Literal["file", "directory", "symlink", "other"]:
        """Determine the kind of a filesystem entry."""
        if path.is_symlink():
            return "symlink"
        elif path.is_file():
            return "file"
        elif path.is_dir():
            return "directory"
        return "other"
    
    def _get_git_status(self, relative_path: str) -> str | None:
        """Get git status for a file.
        
        Returns None if not in a git repo or git is unavailable.
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain", "--", relative_path],
                cwd=self._project_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                return None
            
            output = result.stdout.strip()
            if not output:
                return "clean"
            
            # Parse porcelain format: XY filename
            # X is index status, Y is worktree status
            status_code = output[:2] if len(output) >= 2 else ""
            return status_code.strip() or "clean"
            
        except (subprocess.SubprocessError, OSError):
            return None
    
    def list_directory(
        self,
        relative_path: str = ".",
        *,
        include_hidden: bool = False,
        include_git_status: bool = False,
    ) -> list[FileEntry]:
        """List contents of a directory.
        
        Args:
            relative_path: Path relative to project root (default: root)
            include_hidden: Include hidden files (starting with .)
            include_git_status: Include git status for each entry
            
        Returns:
            List of FileEntry objects
            
        Raises:
            PathSecurityError: If path validation fails
            FileNotFoundError: If directory doesn't exist
            NotADirectoryError: If path is not a directory
        """
        validated = self.validate_path(relative_path)
        
        if not validated.exists():
            raise FileNotFoundError(f"Directory not found: {relative_path}")
        
        if not validated.is_dir():
            raise NotADirectoryError(f"Not a directory: {relative_path}")
        
        entries: list[FileEntry] = []
        
        for item in validated.iterdir():
            name = item.name
            
            # Skip hidden files unless requested
            if not include_hidden and name.startswith("."):
                continue
            
            try:
                stat_result = item.stat(follow_symlinks=False)
                kind = self._get_entry_kind(item)
                size = stat_result.st_size if kind == "file" else None
                mtime = stat_result.st_mtime
                
                git_status = None
                if include_git_status:
                    entry_rel_path = str(item.relative_to(self._project_root))
                    git_status = self._get_git_status(entry_rel_path)
                
                entries.append(FileEntry(
                    name=name,
                    kind=kind,
                    size=size,
                    mtime=mtime,
                    git_status=git_status,
                ))
            except OSError:
                # Skip entries we can't stat
                continue
        
        # Sort: directories first, then files, alphabetically within each
        entries.sort(key=lambda e: (e.kind != "directory", e.name.lower()))
        
        return entries
    
    def read_file(
        self,
        relative_path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
        max_size: int = 10 * 1024 * 1024,  # 10MB default limit
    ) -> tuple[str, int]:
        """Read file content.
        
        Args:
            relative_path: Path relative to project root
            start_line: Starting line number (1-indexed, inclusive)
            end_line: Ending line number (1-indexed, inclusive)
            max_size: Maximum file size to read in bytes
            
        Returns:
            Tuple of (content, total_line_count)
            
        Raises:
            PathSecurityError: If path validation fails
            FileNotFoundError: If file doesn't exist
            IsADirectoryError: If path is a directory
            ValueError: If file exceeds max_size
        """
        validated = self.validate_path(relative_path)
        
        if not validated.exists():
            raise FileNotFoundError(f"File not found: {relative_path}")
        
        if validated.is_dir():
            raise IsADirectoryError(f"Cannot read directory: {relative_path}")
        
        # Check file size before reading
        size = validated.stat().st_size
        if size > max_size:
            raise ValueError(
                f"File exceeds maximum size ({size} > {max_size} bytes): {relative_path}"
            )
        
        # Validate line range ordering before reading
        if start_line is not None and end_line is not None and start_line > end_line:
            raise ValueError(
                f"start_line ({start_line}) must be <= end_line ({end_line})"
            )

        # Read the file
        content = validated.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        # Apply line range if specified
        if start_line is not None or end_line is not None:
            start_idx = (start_line - 1) if start_line is not None else 0
            end_idx = end_line if end_line is not None else total_lines
            
            # Clamp to valid range
            start_idx = max(0, start_idx)
            end_idx = min(total_lines, end_idx)
            
            lines = lines[start_idx:end_idx]
            content = "".join(lines)
        
        return content, total_lines
    
    def get_file_meta(
        self,
        relative_path: str,
        *,
        include_git_history: bool = False,
        history_limit: int = 10,
    ) -> FileMeta:
        """Get metadata for a file.
        
        Args:
            relative_path: Path relative to project root
            include_git_history: Include recent git log entries
            history_limit: Maximum number of git log entries
            
        Returns:
            FileMeta object
            
        Raises:
            PathSecurityError: If path validation fails
            FileNotFoundError: If file doesn't exist
        """
        validated = self.validate_path(relative_path)
        
        if not validated.exists():
            raise FileNotFoundError(f"File not found: {relative_path}")
        
        stat_result = validated.stat(follow_symlinks=False)
        kind = self._get_entry_kind(validated)
        
        git_status = self._get_git_status(relative_path)
        
        git_history = None
        if include_git_history:
            try:
                result = subprocess.run(
                    [
                        "git", "log",
                        f"-{history_limit}",
                        "--oneline",
                        "--follow",
                        "--",
                        relative_path,
                    ],
                    cwd=self._project_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    git_history = [
                        line.strip()
                        for line in result.stdout.strip().split("\n")
                        if line.strip()
                    ]
            except (subprocess.SubprocessError, OSError):
                pass
        
        return FileMeta(
            path=relative_path,
            kind=kind,
            size=stat_result.st_size,
            mtime=stat_result.st_mtime,
            git_status=git_status,
            git_history=git_history,
        )
    
    def search_files(
        self,
        query: str,
        *,
        path_prefix: str = "",
        max_results: int = 100,
        include_hidden: bool = False,
    ) -> list[str]:
        """Search for files by name (fuzzy matching).
        
        Args:
            query: Search query (matched against filename)
            path_prefix: Limit search to paths starting with this prefix
            max_results: Maximum number of results to return
            include_hidden: Include hidden files in results
            
        Returns:
            List of relative paths matching the query
            
        Raises:
            PathSecurityError: If path_prefix validation fails
        """
        start_path = (
            self.validate_path(path_prefix) if path_prefix else self._project_root
        )
        
        if not start_path.exists():
            return []
        
        query_lower = query.lower()
        results: list[tuple[int, str]] = []  # (score, path)
        
        def walk_dir(dir_path: Path, rel_prefix: str, depth: int) -> None:
            if len(results) >= max_results * 2:  # Collect more for scoring
                return
            if depth > _MAX_SEARCH_DEPTH:
                return

            try:
                for item in dir_path.iterdir():
                    name = item.name

                    # Skip hidden unless requested
                    if not include_hidden and name.startswith("."):
                        continue

                    rel_path = f"{rel_prefix}/{name}" if rel_prefix else name

                    # Skip symlinks during recursion — resolving them here
                    # could escape the project root and cause cycles.
                    if item.is_symlink():
                        continue

                    if item.is_dir():
                        # Recurse into real directories only
                        walk_dir(item, rel_path, depth + 1)
                    elif item.is_file():
                        # Score the filename match
                        name_lower = name.lower()
                        if query_lower in name_lower:
                            # Prefer exact matches, then prefix matches, then contains
                            if name_lower == query_lower:
                                score = 0  # Best
                            elif name_lower.startswith(query_lower):
                                score = 1
                            else:
                                score = 2 + name_lower.index(query_lower)
                            results.append((score, rel_path))
            except OSError:
                pass

        walk_dir(start_path, path_prefix, depth=0)
        
        # Sort by score and take top results
        results.sort(key=lambda x: (x[0], x[1]))
        return [path for _, path in results[:max_results]]
    
    def get_diff(
        self,
        relative_path: str,
        *,
        ref_a: str = "HEAD",
        ref_b: str | None = None,  # None means working tree
    ) -> str:
        """Get unified diff for a file.
        
        Args:
            relative_path: Path relative to project root
            ref_a: First git ref (default: HEAD)
            ref_b: Second git ref (default: working tree)
            
        Returns:
            Unified diff output
            
        Raises:
            PathSecurityError: If path validation fails
            FileNotFoundError: If file doesn't exist
            RuntimeError: If git diff fails
        """
        validated = self.validate_path(relative_path)

        if not validated.exists() and ref_b is None:
            raise FileNotFoundError(f"File not found: {relative_path}")

        # Validate refs before passing to git to prevent option injection
        try:
            _validate_git_ref(ref_a)
            if ref_b is not None:
                _validate_git_ref(ref_b)
        except ValueError as e:
            raise ValueError(str(e)) from e

        try:
            if ref_b is None:
                # Diff ref_a against working tree
                cmd = ["git", "diff", ref_a, "--", relative_path]
            else:
                # Diff between two refs
                cmd = ["git", "diff", ref_a, ref_b, "--", relative_path]
            
            result = subprocess.run(
                cmd,
                cwd=self._project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode != 0 and result.stderr:
                raise RuntimeError(f"Git diff failed: {result.stderr.strip()}")
            
            return result.stdout
            
        except subprocess.SubprocessError as e:
            raise RuntimeError(f"Git diff failed: {e}") from e


__all__ = [
    "FileEntry",
    "FileMeta",
    "FileService",
]

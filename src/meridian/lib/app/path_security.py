"""Path security validation for project-scoped file operations.

All file endpoints in the app server must validate paths through this module
to ensure they remain within the project root boundary.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


class PathSecurityError(Exception):
    """Raised when a path fails security validation.
    
    Route handlers should catch this and return 400/403 status codes.
    """
    pass


# Patterns for detecting Windows-style paths and UNC paths
# Matches "C:" with or without a following slash — covers both absolute
# (C:\foo, C:/foo) and drive-relative (C:foo) forms.
_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _normalize_separators(path: str) -> str:
    """Convert Windows backslashes to forward slashes."""
    return path.replace("\\", "/")


def _is_windows_absolute(path: str) -> bool:
    """Check if path looks like a Windows absolute path."""
    return bool(_WINDOWS_DRIVE_RE.match(path))


def _is_unc_path(path: str) -> bool:
    """Check if path looks like a UNC path."""
    return path.startswith("\\\\")


def validate_project_path(
    project_root: Path,
    relative_path: str,
    *,
    resolve_symlinks: bool = True,
) -> Path:
    """Validate and resolve a project-root-relative path.
    
    Args:
        project_root: The project root directory (must be absolute)
        relative_path: User-provided path (must be relative to project root)
        resolve_symlinks: Whether to resolve symlinks and check for escape
    
    Returns:
        Resolved absolute Path within project root
        
    Raises:
        PathSecurityError: If path escapes project root or is invalid
        
    Security guarantees:
        - Rejects absolute POSIX paths (starting with /)
        - Rejects Windows drive letters (C:\\, D:/)
        - Rejects UNC paths (\\\\server\\share)
        - Rejects parent escapes via .. components
        - Rejects symlinks resolving outside project root (if resolve_symlinks=True)
        - Rejects paths containing null bytes
    """
    # Validate inputs
    if not project_root.is_absolute():
        raise PathSecurityError("project_root must be absolute")
    
    # Check for null bytes (security risk in some systems)
    if "\x00" in relative_path:
        raise PathSecurityError("Path contains null bytes")
    
    # Check for empty path
    if not relative_path or relative_path.strip() == "":
        raise PathSecurityError("Path cannot be empty")
    
    # Check UNC paths BEFORE normalizing (they start with \\)
    if _is_unc_path(relative_path):
        raise PathSecurityError(f"UNC paths not allowed: {relative_path}")
    
    # Check Windows drive letters BEFORE normalizing
    if _is_windows_absolute(relative_path):
        raise PathSecurityError(f"Windows absolute paths not allowed: {relative_path}")
    
    # Normalize separators for cross-platform handling
    normalized = _normalize_separators(relative_path)
    
    # Reject absolute POSIX paths
    if normalized.startswith("/"):
        raise PathSecurityError(f"Absolute paths not allowed: {relative_path}")
    
    # Build the target path
    # Use project_root / normalized to join paths safely
    try:
        # Resolve the project root first
        resolved_root = project_root.resolve()
        
        # Build the candidate path
        candidate = resolved_root / normalized
        
        # Normalize the path (resolve . and .. without following symlinks yet)
        # We need to check if the normalized path escapes before resolving symlinks
        # because .. can escape even without symlinks
        try:
            # Use os.path.normpath to handle .. without resolving symlinks
            normalized_candidate = Path(os.path.normpath(str(candidate)))
        except (ValueError, OSError) as e:
            raise PathSecurityError(f"Invalid path: {relative_path}") from e
        
        # Check if normalized path stays within project root
        # This catches parent escapes via ..
        try:
            # Check if the normalized path starts with the resolved root
            normalized_candidate.relative_to(resolved_root)
        except ValueError:
            raise PathSecurityError(
                f"Path escapes project root via parent reference: {relative_path}"
            ) from None
        
        # Now handle symlinks if requested
        if resolve_symlinks:
            # Always resolve — Path.resolve(strict=False) handles non-existent
            # paths without raising, eliminating the TOCTOU race that exists()
            # then resolve() would introduce.
            try:
                resolved_candidate = normalized_candidate.resolve()
            except (OSError, RuntimeError) as e:
                # Handle cases like circular symlinks
                raise PathSecurityError(f"Cannot resolve path: {e}") from e

            # Check if resolved path is still within project root
            try:
                resolved_candidate.relative_to(resolved_root)
            except ValueError:
                raise PathSecurityError(
                    f"Symlink escapes project root: {relative_path}"
                ) from None

            return resolved_candidate
        else:
            return normalized_candidate
            
    except PathSecurityError:
        raise
    except Exception as e:
        raise PathSecurityError(f"Path validation failed: {e}") from e


def is_safe_relative_path(relative_path: str) -> bool:
    """Quick check if a path string looks safe (no escapes, not absolute).
    
    This is a fast pre-check that doesn't require a project root.
    Always use validate_project_path() for actual validation.
    """
    if not relative_path:
        return False
    
    if "\x00" in relative_path:
        return False
    
    # Check UNC before normalizing
    if _is_unc_path(relative_path):
        return False
    
    # Check Windows drive letters before normalizing
    if _is_windows_absolute(relative_path):
        return False
    
    normalized = _normalize_separators(relative_path)
    
    # Reject absolute paths
    if normalized.startswith("/"):
        return False
    
    # Check for obvious parent escapes
    # This is conservative - validate_project_path does the real check
    parts = normalized.split("/")
    depth = 0
    for part in parts:
        if part == "..":
            depth -= 1
            if depth < 0:
                return False
        elif part and part != ".":
            depth += 1
    
    return True


__all__ = [
    "PathSecurityError",
    "is_safe_relative_path",
    "validate_project_path",
]

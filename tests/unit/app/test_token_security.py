"""Regression tests for token file permissions."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


def _write_token_file(token_file: Path, token: str) -> None:
    """Mirror the token write pattern used by the app lifespan."""
    token_fd = os.open(
        str(token_file),
        os.O_CREAT | os.O_WRONLY | os.O_TRUNC,
        0o600,
    )
    try:
        os.fchmod(token_fd, 0o600)  # Defense-in-depth for PID reuse.
        os.write(token_fd, token.encode("utf-8"))
        os.fsync(token_fd)
    finally:
        os.close(token_fd)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits do not apply")
def test_token_file_mode_under_zero_umask(tmp_path: Path) -> None:
    """Token file must stay 0o600 even when process umask is fully permissive."""
    token_file = tmp_path / "token"
    original_umask = os.umask(0o000)
    try:
        _write_token_file(token_file, "secret-token")
    finally:
        os.umask(original_umask)

    mode = os.stat(token_file).st_mode & 0o777
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX mode bits do not apply")
def test_token_file_mode_tightened_on_pid_reuse(tmp_path: Path) -> None:
    """Token file must be tightened to 0o600 even if pre-existing file has looser permissions."""
    token_file = tmp_path / "token"
    # Create pre-existing file with loose permissions (simulates stale token surviving crash).
    token_file.write_text("old-token")
    os.chmod(token_file, 0o644)
    assert (os.stat(token_file).st_mode & 0o777) == 0o644, (
        "precondition: file starts at 0o644"
    )

    # Write new token (simulates new server instance reusing PID).
    _write_token_file(token_file, "new-secret-token")

    # Verify permissions are tightened.
    mode = os.stat(token_file).st_mode & 0o777
    assert mode == 0o600, f"expected 0o600 after overwrite, got {oct(mode)}"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific behavior")
def test_token_file_windows_acl_limitation() -> None:
    """Document Windows token-file security constraints.

    On Windows, token-file protection relies on per-user directory ACLs rather
    than POSIX mode bits.
    """
    pass

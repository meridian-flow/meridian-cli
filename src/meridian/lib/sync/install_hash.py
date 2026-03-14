"""Hash helpers for the managed install model."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _format_hash(data: bytes) -> str:
    return f"sha256:{_sha256_hex(data)}"


def _normalized_text_bytes(text: str) -> bytes:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"
    return normalized.encode("utf-8")


def _read_visible_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    return _normalized_text_bytes(text)


def _iter_relative_files(directory: Path) -> list[str]:
    relative_paths: list[str] = []

    for root, dirnames, filenames in os.walk(directory, topdown=True, followlinks=False):
        root_path = Path(root)

        retained_dirnames: list[str] = []
        for dirname in dirnames:
            if dirname == ".git":
                continue
            dir_path = root_path / dirname
            if dir_path.is_symlink():
                relative_path = dir_path.relative_to(directory).as_posix()
                raise ValueError(f"Symlinks are not supported: {relative_path}")
            retained_dirnames.append(dirname)
        dirnames[:] = retained_dirnames

        for filename in filenames:
            file_path = root_path / filename
            if file_path.is_symlink():
                relative_path = file_path.relative_to(directory).as_posix()
                raise ValueError(f"Symlinks are not supported: {relative_path}")
            relative_paths.append(file_path.relative_to(directory).as_posix())

    relative_paths.sort()
    return relative_paths


def compute_visible_file_hash(path: Path) -> str:
    """Hash one file using normalized visible content."""

    return _format_hash(_read_visible_bytes(path))


def compute_visible_tree_hash(directory: Path) -> str:
    """Hash one directory tree using normalized visible file content."""

    manifest: list[str] = []
    for relative_path in _iter_relative_files(directory):
        path = directory / relative_path
        digest = _sha256_hex(_read_visible_bytes(path))
        manifest.append(f"{relative_path}\0{digest}\n")
    return _format_hash("".join(manifest).encode("utf-8"))


def compute_install_item_hash(path: Path, item_kind: str) -> str:
    """Dispatch to the appropriate managed-install hash strategy."""

    if item_kind == "agent":
        return compute_visible_file_hash(path)
    if item_kind == "skill":
        return compute_visible_tree_hash(path)
    raise ValueError(f"Unsupported managed item kind: {item_kind}")

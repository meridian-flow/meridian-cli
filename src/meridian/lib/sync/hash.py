"""Content hashing helpers for sync-managed agents and skills."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import frontmatter  # type: ignore[import-untyped]


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _format_hash(data: bytes) -> str:
    return f"sha256:{_sha256_hex(data)}"


def _load_markdown_body(path: Path) -> str:
    with path.open(encoding="utf-8") as handle:
        post = frontmatter.load(handle)
    return str(post.content)


def compute_file_body_hash(path: Path) -> str:
    """Compute a body-only hash for one markdown file."""

    return _format_hash(_load_markdown_body(path).encode("utf-8"))


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


def compute_tree_hash(directory: Path, entry_point: str = "SKILL.md") -> str:
    """Compute a deterministic tree hash for a skill directory."""

    manifest: list[str] = []
    for relative_path in _iter_relative_files(directory):
        path = directory / relative_path
        if relative_path == entry_point:
            digest = _sha256_hex(_load_markdown_body(path).encode("utf-8"))
        else:
            digest = _sha256_hex(path.read_bytes())
        manifest.append(f"{relative_path}\0{digest}\n")
    return _format_hash("".join(manifest).encode("utf-8"))


def compute_item_hash(path: Path, item_kind: str) -> str:
    """Dispatch to the appropriate hashing strategy for a sync item."""

    if item_kind == "skill":
        return compute_tree_hash(path)
    if item_kind == "agent":
        return compute_file_body_hash(path)
    raise ValueError(f"Unsupported item kind: {item_kind}")

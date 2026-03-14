"""Adapter seams for managed source kinds."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.sync.install_config import ManagedSourceConfig
from meridian.lib.sync.install_types import SourceKind
from meridian.lib.sync.source_manifest import ExportedSourceManifest, load_source_manifest


class ResolvedSource(BaseModel):
    """Resolved source metadata plus a local tree path."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    kind: SourceKind
    locator: str
    requested_ref: str | None = None
    resolved_identity: dict[str, object] = Field(default_factory=dict)
    tree_path: Path


class SourceAdapter(Protocol):
    """Small adapter interface for one managed source kind."""

    kind: SourceKind

    def resolve(
        self,
        source: ManagedSourceConfig,
        *,
        cache_dir: Path,
        repo_root: Path,
        locked_identity: dict[str, object] | None = None,
        upgrade: bool = False,
    ) -> ResolvedSource: ...

    def fetch(self, resolved: ResolvedSource) -> Path: ...

    def describe(self, tree_path: Path) -> ExportedSourceManifest: ...


class GitSourceAdapter:
    """Placeholder adapter for git-backed sources."""

    kind: SourceKind = "git"

    def resolve(
        self,
        source: ManagedSourceConfig,
        *,
        cache_dir: Path,
        repo_root: Path,
        locked_identity: dict[str, object] | None = None,
        upgrade: bool = False,
    ) -> ResolvedSource:
        _ = cache_dir
        _ = repo_root
        _ = locked_identity
        _ = upgrade
        if source.url is None:
            raise ValueError("Git source resolution requires 'url'.")
        raise NotImplementedError("Git managed-source resolution lands in the install-engine slice.")

    def fetch(self, resolved: ResolvedSource) -> Path:
        return resolved.tree_path

    def describe(self, tree_path: Path) -> ExportedSourceManifest:
        return load_source_manifest(tree_path)


class PathSourceAdapter:
    """Minimal adapter for local path sources."""

    kind: SourceKind = "path"

    def resolve(
        self,
        source: ManagedSourceConfig,
        *,
        cache_dir: Path,
        repo_root: Path,
        locked_identity: dict[str, object] | None = None,
        upgrade: bool = False,
    ) -> ResolvedSource:
        _ = cache_dir
        _ = locked_identity
        _ = upgrade
        if source.path is None:
            raise ValueError("Path source resolution requires 'path'.")

        configured = Path(source.path).expanduser()
        tree_path = configured if configured.is_absolute() else repo_root / configured
        return ResolvedSource(
            source_name=source.name,
            kind="path",
            locator=source.path,
            tree_path=tree_path.resolve(),
            resolved_identity={"path": source.path},
        )

    def fetch(self, resolved: ResolvedSource) -> Path:
        return resolved.tree_path

    def describe(self, tree_path: Path) -> ExportedSourceManifest:
        return load_source_manifest(tree_path)


def default_source_adapters() -> dict[SourceKind, SourceAdapter]:
    """Return the default adapter registry."""

    return {
        "git": GitSourceAdapter(),
        "path": PathSourceAdapter(),
    }

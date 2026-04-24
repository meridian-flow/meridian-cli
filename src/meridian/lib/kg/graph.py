"""KG graph analysis — build AnalysisResult from markdown files."""

from __future__ import annotations

import os
from collections import deque
from pathlib import Path
from typing import Any, cast

import pathspec

from meridian.lib.kg.types import AnalysisResult, GraphEdge, GraphNode
from meridian.lib.markdown.extract import extract_file
from meridian.lib.markdown.types import ExtractedLink

# Directories to skip when walking
_SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    "dist",
    "build",
    ".ruff_cache",
}

# External URL prefixes — not checked for broken links
_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "#")


def build_analysis(
    root: Path,
    *,
    include_backlinks: bool = True,
    include_clusters: bool = True,
    targeted_path: Path | None = None,
    exclude: list[str] | None = None,
) -> AnalysisResult:
    """Build complete KG analysis from a root directory.

    Args:
        root: Root directory to scan for .md files
        include_backlinks: Whether to compute missing backlinks
        include_clusters: Whether to compute connected clusters
        targeted_path: If set, only analyze this file/directory (for kg check)

    Returns:
        AnalysisResult with nodes, edges, broken_links, orphans, etc.
    """
    root = root.resolve()

    # Collect markdown files
    if targeted_path is not None:
        targeted = targeted_path.resolve()
        if targeted.is_file():
            md_files = [targeted]
            scan_root = targeted.parent
        else:
            md_files = _collect_md_files(targeted, exclude=exclude)
            scan_root = targeted
    else:
        md_files = _collect_md_files(root, exclude=exclude)
        scan_root = root

    # Build nodes dict
    nodes: dict[Path, GraphNode] = {}
    for md_path in md_files:
        doc = extract_file(md_path)
        rel_path = _rel_posix(md_path, scan_root)
        nodes[md_path] = GraphNode(doc=doc, rel_path=rel_path, in_degree=0)

    # Build edges and track inbound links
    edges: list[GraphEdge] = []
    broken_links: list[GraphEdge] = []
    inbound: dict[Path, set[Path]] = {p: set() for p in nodes}
    external_count = 0

    for src_path, node in nodes.items():
        for ref in node.doc.references:
            edge = _make_edge(src_path, ref, nodes)
            edges.append(edge)

            if _is_external(ref.target):
                external_count += 1
            elif not edge.resolved:
                broken_links.append(edge)
            elif isinstance(edge.dst, Path) and edge.dst in nodes:
                inbound[edge.dst].add(src_path)

    # Compute in_degree for each node
    for target_path, sources in inbound.items():
        nodes[target_path].in_degree = len(sources)

    # Orphan detection removed from output; retain field for compatibility.
    orphans: list[Path] = []

    # Missing backlinks (A→B but no B→A)
    missing_backlinks: list[tuple[Path, Path]] = []
    if include_backlinks:
        for src_path, node in nodes.items():
            for ref in node.doc.references:
                if isinstance(ref.resolved, Path) and ref.resolved in nodes:
                    target = ref.resolved
                    # Check if target links back to src
                    target_links_back = any(
                        r.resolved == src_path for r in nodes[target].doc.references
                    )
                    if not target_links_back:
                        pair = (src_path, target)
                        if pair not in missing_backlinks:
                            missing_backlinks.append(pair)

    # Compute connected clusters via BFS
    clusters: list[list[Path]] = []
    if include_clusters:
        clusters = _compute_clusters(nodes, inbound)

    return AnalysisResult(
        nodes=nodes,
        edges=edges,
        broken_links=broken_links,
        orphans=orphans,
        missing_backlinks=missing_backlinks,
        clusters=clusters,
        external_count=external_count,
    )


def _is_external(target: str) -> bool:
    """Check if a target is an external URL."""
    return any(target.startswith(prefix) for prefix in _EXTERNAL_PREFIXES)


def _load_kgignore(root: Path) -> pathspec.PathSpec[Any] | None:
    """Read .kgignore from root dir, return compiled PathSpec or None."""
    kgignore = root / ".kgignore"
    if not kgignore.exists():
        return None

    lines = kgignore.read_text(encoding="utf-8", errors="replace").splitlines()
    patterns = [
        line.strip()
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]
    if not patterns:
        return None
    return cast(
        "pathspec.PathSpec[Any]",
        pathspec.PathSpec.from_lines("gitwildmatch", patterns),  # pyright: ignore[reportUnknownMemberType]
    )


def _collect_md_files(
    root: Path,
    *,
    exclude: list[str] | None = None,
) -> list[Path]:
    """Walk directory and collect .md files, applying skip dirs and exclusions."""
    kgignore_spec = _load_kgignore(root)

    exclude_spec: pathspec.PathSpec[Any] | None = None
    if exclude:
        exclude_spec = cast(
            "pathspec.PathSpec[Any]",
            pathspec.PathSpec.from_lines("gitwildmatch", exclude),  # pyright: ignore[reportUnknownMemberType]
        )

    md_files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories in-place
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

        for filename in filenames:
            if not filename.endswith(".md"):
                continue

            full_path = Path(dirpath) / filename
            rel = full_path.relative_to(root).as_posix()

            if kgignore_spec and kgignore_spec.match_file(rel):
                continue
            if exclude_spec and exclude_spec.match_file(rel):
                continue

            md_files.append(full_path)

    return sorted(md_files)


def _make_edge(
    src_path: Path,
    ref: ExtractedLink,
    nodes: dict[Path, GraphNode],
) -> GraphEdge:
    """Convert an ExtractedLink to a GraphEdge."""
    _ = nodes  # Available for future use (e.g., node-aware resolution)

    resolved: bool
    dst: Path | str

    if ref.resolved is not None:
        dst = ref.resolved
        resolved = ref.resolved.exists()
    else:
        # Wikilinks or external — store as raw string
        dst = ref.target
        # External links are "resolved" (we just don't check them)
        resolved = _is_external(ref.target)

    return GraphEdge(
        src=src_path,
        dst=dst,
        kind=ref.kind,
        resolved=resolved,
        line=ref.line,
    )


def _compute_clusters(
    nodes: dict[Path, GraphNode], inbound: dict[Path, set[Path]]
) -> list[list[Path]]:
    """Compute connected components via BFS over bidirectional adjacency."""
    # Build bidirectional adjacency
    adj: dict[Path, set[Path]] = {p: set() for p in nodes}
    for target, sources in inbound.items():
        for src in sources:
            adj[src].add(target)
            adj[target].add(src)

    visited: set[Path] = set()
    clusters: list[list[Path]] = []

    for start in nodes:
        if start in visited:
            continue
        # BFS from start
        component: list[Path] = []
        queue: deque[Path] = deque([start])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            for neighbor in adj[current]:
                if neighbor not in visited:
                    queue.append(neighbor)
        # Only include non-singleton clusters (singletons are orphans)
        if len(component) > 1:
            clusters.append(sorted(component))

    return clusters


def _rel_posix(path: Path, root: Path) -> str:
    """Get path relative to root as forward-slash string."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


__all__ = ["build_analysis"]

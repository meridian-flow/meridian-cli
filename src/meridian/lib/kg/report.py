"""Plain-text report formatting for KB analysis results."""

from __future__ import annotations

from pathlib import Path

from meridian.lib.kb.types import AnalysisResult


def format_report(
    result: AnalysisResult,
    root: Path,
    *,
    targeted: bool = False,
) -> str:
    """Format AnalysisResult as plain-text report.

    Args:
        result: Analysis result to format
        root: Root path for relative path display
        targeted: If True, format as targeted check (single file/dir)

    Returns:
        Plain text report string
    """
    lines: list[str] = []

    # Header
    lines.append(f"## KB Analysis: {root.as_posix()}")
    lines.append(f"Files scanned: {len(result.nodes)}")
    lines.append(f"Total links: {len(result.edges)}")
    lines.append("")

    # Broken Links section
    lines.append("## Broken Links")
    if result.broken_links:
        for edge in result.broken_links:
            src_rel = _rel(edge.src, root)
            target_str = str(edge.dst) if isinstance(edge.dst, str) else _rel(edge.dst, root)
            lines.append(f"  {src_rel}:{edge.line} -> {target_str} [{edge.kind}]")
    else:
        lines.append("  None")
    lines.append("")

    # Orphaned Files section
    lines.append("## Orphaned Files")
    lines.append("  (Documents with no inbound links)")
    if result.orphans:
        for orphan in result.orphans:
            lines.append(f"  - {_rel(orphan, root)}")
    else:
        lines.append("  None")
    lines.append("")

    # Missing Backlinks section (skip for targeted check)
    if not targeted and result.missing_backlinks:
        lines.append("## Missing Backlinks")
        lines.append("  (A links to B, but B does not link back to A)")
        for src, dst in result.missing_backlinks:
            lines.append(f"  {_rel(src, root)} -> {_rel(dst, root)}")
        lines.append("")

    # Connected Clusters section (skip singletons and targeted check)
    if not targeted and result.clusters:
        lines.append("## Connected Clusters")
        lines.append("  (Groups of documents connected by links)")
        for i, cluster in enumerate(result.clusters, 1):
            lines.append(f"  Cluster {i} ({len(cluster)} files):")
            for member in cluster:
                lines.append(f"    - {_rel(member, root)}")
        lines.append("")

    # Source Coverage section
    if result.coverage:
        cov = result.coverage
        total = len(cov.covered) + len(cov.uncovered)
        pct = round(len(cov.covered) / total * 100, 1) if total > 0 else 0.0

        lines.append("## Source Coverage")
        lines.append(f"  Source roots: {', '.join(sr.as_posix() for sr in cov.source_roots)}")
        lines.append(f"  Coverage: {len(cov.covered)}/{total} files ({pct}%)")
        lines.append("")

        if cov.uncovered:
            lines.append("  Uncovered files:")
            for path in cov.uncovered:
                # Show relative to first source root if possible
                rel = _rel_to_any(path, cov.source_roots)
                lines.append(f"    - {rel}")
            lines.append("")

        # Symbol edges
        if cov.symbol_edges:
            lines.append("## Symbol References")
            for se in cov.symbol_edges:
                doc_rel = _rel(se.doc_path, root)
                src_rel = _rel_to_any(se.src_file, cov.source_roots)
                lines.append(f"  {doc_rel} -> {src_rel}:{se.symbol_name} (line {se.symbol_line})")
            lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(f"  Total files: {len(result.nodes)}")
    lines.append(f"  Total links: {len(result.edges)}")
    lines.append(f"  Broken links: {len(result.broken_links)}")
    lines.append(f"  Orphans: {len(result.orphans)}")
    if not targeted:
        lines.append(f"  Missing backlinks: {len(result.missing_backlinks)}")
        lines.append(f"  Clusters: {len(result.clusters)}")
    if result.coverage:
        total = len(result.coverage.covered) + len(result.coverage.uncovered)
        pct = round(len(result.coverage.covered) / total * 100, 1) if total > 0 else 0.0
        lines.append(f"  Source coverage: {pct}%")

    return "\n".join(lines)


def _rel(path: Path, root: Path) -> str:
    """Get path relative to root as forward-slash string."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _rel_to_any(path: Path, roots: list[Path]) -> str:
    """Get path relative to any of the given roots."""
    for root in roots:
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            continue
    return path.as_posix()


__all__ = ["format_report"]

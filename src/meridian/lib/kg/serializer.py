"""JSON serialization for KB analysis results.

Provides the stable JSON contract for API routes and machine consumers.
All paths are expressed as strings relative to root, using forward slashes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from meridian.lib.kb.types import AnalysisResult, CoverageResult


def serialize_analysis(result: AnalysisResult, root: Path) -> dict[str, Any]:
    """Serialize AnalysisResult to JSON-safe dict.

    All paths are expressed as strings relative to root, using forward slashes.
    """
    return {
        "root": root.as_posix(),
        "total_files": len(result.nodes),
        "total_links": len(result.edges),
        "has_broken_links": len(result.broken_links) > 0,
        "broken_links": [
            {
                "source": _rel(edge.src, root),
                "target": str(edge.dst) if isinstance(edge.dst, str) else _rel(edge.dst, root),
                "line": edge.line,
                "kind": edge.kind,
            }
            for edge in result.broken_links
        ],
        "orphans": [_rel(p, root) for p in result.orphans],
        "missing_backlinks": [
            [_rel(a, root), _rel(b, root)] for a, b in result.missing_backlinks
        ],
        "clusters": [
            [_rel(p, root) for p in cluster] for cluster in result.clusters
        ],
        "coverage": _serialize_coverage(result.coverage, root) if result.coverage else None,
        "summary": {
            "total_files": len(result.nodes),
            "total_links": len(result.edges),
            "broken_links": len(result.broken_links),
            "orphans": len(result.orphans),
            "missing_backlinks": len(result.missing_backlinks),
            "clusters": len(result.clusters),
        },
    }


def serialize_check(result: AnalysisResult, path: Path) -> dict[str, Any]:
    """Serialize a targeted check result for kb check command.

    Focused output for single file or directory analysis.
    """
    root = path if path.is_dir() else path.parent

    # Collect all outbound links from the analyzed documents
    outbound_links: list[dict[str, Any]] = []
    fenced_blocks: list[dict[str, Any]] = []

    for node in result.nodes.values():
        doc = node.doc
        if doc.error:
            continue

        for ref in doc.references:
            outbound_links.append(
                {
                    "target": ref.target,
                    "kind": ref.kind,
                    "line": ref.line,
                    "text": ref.text,
                }
            )

        for block in doc.fenced_blocks:
            fenced_blocks.append(
                {
                    "language": block.language,
                    "start_line": block.start_line,
                    "lines": len(block.content.split("\n")),
                }
            )

    return {
        "path": path.as_posix(),
        "total_files": len(result.nodes),
        "has_broken_links": len(result.broken_links) > 0,
        "broken_links": [
            {
                "source": _rel(edge.src, root),
                "target": str(edge.dst) if isinstance(edge.dst, str) else _rel(edge.dst, root),
                "line": edge.line,
                "kind": edge.kind,
            }
            for edge in result.broken_links
        ],
        "outbound_links": outbound_links,
        "fenced_blocks": fenced_blocks,
    }


def _serialize_coverage(coverage: CoverageResult, root: Path) -> dict[str, Any]:
    """Serialize coverage result to JSON-safe dict."""
    total_files = len(coverage.covered) + len(coverage.uncovered)
    coverage_pct = (
        round(len(coverage.covered) / total_files * 100, 1)
        if total_files > 0
        else 0.0
    )

    return {
        "source_roots": [sr.as_posix() for sr in coverage.source_roots],
        "total_source_files": total_files,
        "covered_count": len(coverage.covered),
        "uncovered_count": len(coverage.uncovered),
        "coverage_percent": coverage_pct,
        "covered": [
            {"file": _rel(path, root), "confidence": conf}
            for path, conf in coverage.covered
        ],
        "uncovered": [_rel(path, root) for path in coverage.uncovered],
        "symbol_edges": [
            {
                "doc": _rel(se.doc_path, root),
                "source_file": _rel(se.src_file, root),
                "symbol": se.symbol_name,
                "line": se.symbol_line,
            }
            for se in coverage.symbol_edges
        ],
    }


def _rel(path: Path, root: Path) -> str:
    """Get path relative to root as forward-slash string."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


__all__ = [
    "serialize_analysis",
    "serialize_check",
]

"""Typed models for KB graph analysis.

These types are KB-specific. Extraction types live in lib/markdown/types.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from meridian.lib.markdown.types import ExtractedDocument


@dataclass
class GraphNode:
    """One document in the knowledge base graph."""

    doc: ExtractedDocument
    rel_path: str  # path relative to root (display key), forward slashes
    in_degree: int = 0  # count of inbound links (computed)


@dataclass
class GraphEdge:
    """Directed edge in the document graph."""

    src: Path  # source document
    dst: Path | str  # resolved Path for local links; raw str for wikilinks/unresolved
    kind: str  # "md_link" | "image" | "wikilink"
    resolved: bool  # True if dst exists on filesystem
    line: int  # source line number
    confidence: float = 1.0  # 1.0 for explicit links; <1.0 for coverage inference


@dataclass
class SymbolEdge:
    """A resolved reference from a document to a source code symbol."""

    doc_path: Path  # markdown file
    src_file: Path  # source file
    symbol_name: str  # function or class name
    symbol_line: int  # line number in source file


@dataclass
class CoverageResult:
    """Source-file coverage analysis results."""

    covered: list[tuple[Path, float]] = field(default_factory=list)  # (source_file, confidence)
    uncovered: list[Path] = field(default_factory=list)
    source_roots: list[Path] = field(default_factory=list)
    symbol_edges: list[SymbolEdge] = field(default_factory=list)  # populated with --resolve-symbols


@dataclass
class AnalysisResult:
    """Complete KB analysis output."""

    nodes: dict[Path, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    broken_links: list[GraphEdge] = field(default_factory=list)
    orphans: list[Path] = field(default_factory=list)
    missing_backlinks: list[tuple[Path, Path]] = field(default_factory=list)
    clusters: list[list[Path]] = field(default_factory=list)
    coverage: CoverageResult | None = None


__all__ = [
    "AnalysisResult",
    "CoverageResult",
    "GraphEdge",
    "GraphNode",
    "SymbolEdge",
]

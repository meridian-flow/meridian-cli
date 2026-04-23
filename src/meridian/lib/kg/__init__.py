"""Knowledge base analysis: document graph, link health, source coverage."""

from meridian.lib.kb.coverage import compute_coverage
from meridian.lib.kb.graph import build_analysis
from meridian.lib.kb.report import format_report
from meridian.lib.kb.serializer import serialize_analysis, serialize_check
from meridian.lib.kb.symbol_resolver import PythonSymbolResolver, SymbolResolver
from meridian.lib.kb.types import (
    AnalysisResult,
    CoverageResult,
    GraphEdge,
    GraphNode,
    SymbolEdge,
)

__all__ = [
    "AnalysisResult",
    "CoverageResult",
    "GraphEdge",
    "GraphNode",
    "PythonSymbolResolver",
    "SymbolEdge",
    "SymbolResolver",
    "build_analysis",
    "compute_coverage",
    "format_report",
    "serialize_analysis",
    "serialize_check",
]

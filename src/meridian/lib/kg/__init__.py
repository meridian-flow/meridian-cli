"""Knowledge graph analysis: document graph and link health."""

from meridian.lib.kg.graph import build_analysis
from meridian.lib.kg.report import (
    format_check_output,
    format_root_summary,
    format_summary,
    format_tree,
)
from meridian.lib.kg.serializer import serialize_analysis, serialize_check
from meridian.lib.kg.types import (
    AnalysisResult,
    GraphEdge,
    GraphNode,
)

__all__ = [
    "AnalysisResult",
    "GraphEdge",
    "GraphNode",
    "build_analysis",
    "format_check_output",
    "format_root_summary",
    "format_summary",
    "format_tree",
    "serialize_analysis",
    "serialize_check",
]

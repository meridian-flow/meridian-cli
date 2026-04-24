"""JSON serialization for mermaid validation results."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from meridian.lib.mermaid.validator import MermaidValidationResult


def serialize_check(result: MermaidValidationResult, path: Path) -> dict[str, Any]:
    """Serialize validation result to JSON-safe dict."""
    return {
        "path": path.as_posix(),
        "tier": result.tier,
        "total_blocks": result.total_blocks,
        "valid_blocks": result.valid_blocks,
        "invalid_blocks": result.invalid_blocks,
        "has_errors": result.has_errors,
        "results": [
            {
                "file": block.file,
                "line": block.line,
                "valid": block.valid,
                "error": block.error,
                "diagram_type": block.diagram_type,
            }
            for block in result.results
        ],
    }


__all__ = ["serialize_check"]

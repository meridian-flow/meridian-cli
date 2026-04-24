"""Plain-text report formatting for mermaid validation results."""

from __future__ import annotations

from meridian.lib.mermaid.validator import MermaidValidationResult


def format_check_output(result: MermaidValidationResult) -> tuple[str, str]:
    """Format check output. Returns (stdout, stderr)."""
    if not result.has_errors:
        if result.total_blocks == 0:
            return "✓ No mermaid blocks found", ""
        if result.total_blocks == 1:
            return "✓ 1 mermaid block valid", ""
        return f"✓ All {result.total_blocks} mermaid blocks valid", ""

    stdout_lines: list[str] = []
    for block in result.results:
        if not block.valid:
            tier_tag = f" [{block.tier}]" if block.tier == "python" else ""
            error_msg = block.error or "unknown error"
            stdout_lines.append(f"{block.file}:{block.line}: {error_msg}{tier_tag}")

    stdout = "\n".join(stdout_lines)
    stderr = f"{result.invalid_blocks} invalid block(s) found"
    return stdout, stderr


__all__ = ["format_check_output"]

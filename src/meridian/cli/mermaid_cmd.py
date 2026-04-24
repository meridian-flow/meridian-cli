"""CLI handlers for `meridian mermaid` commands."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter

from meridian.cli.app_tree import mermaid_app
from meridian.lib.mermaid.validator import ScanOptions, detect_tier, validate_path


@mermaid_app.default
def cmd_mermaid_root() -> None:
    """Show mermaid validation help and active parser tier."""
    tier = detect_tier()
    tier_desc = "@mermaid-js/parser (node)" if tier == "js" else "python heuristics"
    print(
        f"""Mermaid diagram validation.

Active parser: {tier_desc}

Commands:
  meridian mermaid check           Validate mermaid blocks in current directory
  meridian mermaid check path/     Validate mermaid blocks in directory
  meridian mermaid check file.md   Validate mermaid blocks in file
  meridian mermaid check file.mmd  Validate standalone mermaid file

Options:
  --depth N      Limit directory traversal depth
  --exclude PAT  Exclude paths matching glob pattern (repeatable)
  --format FMT   Output format: text (default) or json"""
    )
    raise SystemExit(0)


@mermaid_app.command(name="check")
def cmd_mermaid_check(
    path: Annotated[
        Path,
        Parameter(help="File or directory to check (default: cwd)."),
    ] = Path("."),
    *,
    depth: Annotated[
        int | None,
        Parameter(name="--depth", help="Max directory traversal depth."),
    ] = None,
    exclude: Annotated[
        list[str] | None,
        Parameter(name="--exclude", help="Glob pattern to exclude (repeatable)."),
    ] = None,
    fmt: Annotated[
        str,
        Parameter(name="--format", help="Output format: text (default) or json."),
    ] = "text",
) -> None:
    """Check mermaid diagram syntax. Exit 0 if clean, exit 1 if errors found."""
    from meridian.cli.main import get_global_options
    from meridian.lib.mermaid.report import format_check_output
    from meridian.lib.mermaid.serializer import serialize_check

    resolved = path.resolve()
    if not resolved.exists():
        print(f"Error: path not found: {path}", file=sys.stderr)
        raise SystemExit(2)

    opts = ScanOptions(
        exclude=exclude or [],
        depth=depth,
    )
    result = validate_path(resolved, opts=opts)

    effective_fmt = "json" if get_global_options().output.format == "json" else fmt

    if effective_fmt == "json":
        import json

        print(json.dumps(serialize_check(result, resolved), indent=2))
    else:
        stdout, stderr = format_check_output(result)
        if stdout:
            print(stdout)
        if stderr:
            print(stderr, file=sys.stderr)

    raise SystemExit(1 if result.has_errors else 0)


__all__ = [
    "cmd_mermaid_check",
    "cmd_mermaid_root",
]

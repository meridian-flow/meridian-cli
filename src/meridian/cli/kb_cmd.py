"""CLI handlers for `meridian kb` commands.

Registers `kb graph` and `kb check` on the shared `kb_app` via
decorator-at-import. Import this module from ``_register_group_commands``
in ``cli/main.py`` to activate the commands.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

from cyclopts import Parameter

from meridian.cli.app_tree import kb_app


@kb_app.command(name="graph")
def cmd_kb_graph(
    root: Annotated[
        Path,
        Parameter(help="Root directory to analyze (default: cwd)."),
    ] = Path("."),
    source: Annotated[
        tuple[Path, ...],
        Parameter(
            name="--source",
            help="Source directory for coverage analysis (repeatable).",
            negative_iterable=(),
        ),
    ] = (),
    source_ext: Annotated[
        tuple[str, ...],
        Parameter(
            name="--source-ext",
            help="Additional file extensions for coverage (repeatable).",
            negative_iterable=(),
        ),
    ] = (),
    no_backlinks: Annotated[
        bool,
        Parameter(name="--no-backlinks", help="Skip missing-backlink analysis."),
    ] = False,
    no_clusters: Annotated[
        bool,
        Parameter(name="--no-clusters", help="Skip connected-cluster analysis."),
    ] = False,
    resolve_symbols: Annotated[
        bool,
        Parameter(
            name="--resolve-symbols",
            help="Use Python AST for symbol-level coverage (requires --source).",
        ),
    ] = False,
) -> None:
    """Analyze document relationships, broken links, orphans, and source coverage."""

    from meridian.lib.kb.graph import build_analysis
    from meridian.lib.kb.report import format_report

    if resolve_symbols and not source:
        print("Warning: --resolve-symbols requires --source; ignoring flag.", file=sys.stderr)
        resolve_symbols = False

    root_resolved = root.resolve()
    if not root_resolved.exists():
        print(f"Error: root not found: {root}", file=sys.stderr)
        raise SystemExit(2)
    if not root_resolved.is_dir():
        print(f"Error: root is not a directory: {root}", file=sys.stderr)
        raise SystemExit(2)

    source_dirs = [s.resolve() for s in source] or None
    source_exts = list(source_ext) or None

    result = build_analysis(
        root=root_resolved,
        source_dirs=source_dirs,
        source_exts=source_exts,
        resolve_symbols=resolve_symbols,
        include_backlinks=not no_backlinks,
        include_clusters=not no_clusters,
    )
    print(format_report(result, root=root_resolved))
    raise SystemExit(1 if result.broken_links else 0)


@kb_app.command(name="check")
def cmd_kb_check(
    path: Annotated[
        Path,
        Parameter(help="File or directory to analyze."),
    ],
) -> None:
    """Quick analysis of a single file or directory.

    Reports broken links, outbound links, and fenced blocks for the
    targeted path.
    """

    from meridian.lib.kb.graph import build_analysis
    from meridian.lib.kb.report import format_report

    resolved = path.resolve()
    if not resolved.exists():
        print(f"Error: path not found: {path}", file=sys.stderr)
        raise SystemExit(2)

    root = resolved if resolved.is_dir() else resolved.parent
    result = build_analysis(
        root=root,
        source_dirs=None,
        targeted_path=resolved,
        include_backlinks=False,
    )
    print(format_report(result, root=root, targeted=True))
    raise SystemExit(1 if result.broken_links else 0)


__all__ = [
    "cmd_kb_check",
    "cmd_kb_graph",
]

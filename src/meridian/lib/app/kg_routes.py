"""KB analysis API route handlers.

Exposes knowledge-base graph analysis through project-root-relative API
endpoints:

- GET /api/kb/graph — full graph analysis as JSON
- GET /api/kb/check — targeted analysis for a single file or directory
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Protocol, cast

from meridian.lib.app.http_types import HTTPExceptionCallable
from meridian.lib.app.path_security import PathSecurityError, validate_project_path


class _FastAPIApp(Protocol):
    """Minimal FastAPI app surface consumed by this module."""

    def get(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...


def register_kb_routes(
    app: object,
    *,
    project_root: Path,
    http_exception: HTTPExceptionCallable,
) -> None:
    """Register ``/api/kb/*`` routes on the FastAPI app.

    All user-supplied paths are validated through ``validate_project_path`` to
    ensure they stay within ``project_root``. Paths that escape the project
    root (absolute paths, UNC, Windows drives, ``..`` traversal) are rejected
    with 403 Forbidden.
    """

    from importlib import import_module

    try:
        fastapi_module = import_module("fastapi")
        Query = fastapi_module.Query
    except ModuleNotFoundError as exc:
        msg = "FastAPI is required for KB routes."
        raise RuntimeError(msg) from exc

    typed_app = cast("_FastAPIApp", app)

    async def kb_graph(
        root: str = Query(default=".", description="Root directory to analyze"),
        source: Annotated[
            list[str] | None,
            Query(description="Source directories for coverage (repeatable)"),
        ] = None,
        source_ext: Annotated[
            list[str] | None,
            Query(description="Additional file extensions (repeatable)"),
        ] = None,
        resolve_symbols: bool = Query(
            default=False,
            description="Use Python AST for symbol resolution",
        ),
        no_backlinks: bool = Query(
            default=False,
            description="Skip missing-backlink analysis",
        ),
        no_clusters: bool = Query(default=False, description="Skip cluster analysis"),
    ) -> dict[str, object]:
        """Analyze document relationships and return the full graph as JSON."""

        from meridian.lib.kb.graph import build_analysis
        from meridian.lib.kb.serializer import serialize_analysis

        try:
            root_path = validate_project_path(project_root, root)
        except PathSecurityError as exc:
            raise http_exception(status_code=403, detail=str(exc)) from exc

        if not root_path.exists():
            raise http_exception(status_code=404, detail=f"root not found: {root}")
        if not root_path.is_dir():
            raise http_exception(status_code=400, detail=f"root is not a directory: {root}")

        source_values = source or []
        source_ext_values = source_ext or []
        try:
            source_dirs = (
                [validate_project_path(project_root, s) for s in source_values] or None
            )
        except PathSecurityError as exc:
            raise http_exception(status_code=403, detail=str(exc)) from exc

        result = build_analysis(
            root=root_path,
            source_dirs=source_dirs,
            source_exts=list(source_ext_values) or None,
            resolve_symbols=resolve_symbols,
            include_backlinks=not no_backlinks,
            include_clusters=not no_clusters,
        )
        return serialize_analysis(result, root_path)

    async def kb_check(
        path: str = Query(..., description="File or directory to analyze"),
    ) -> dict[str, object]:
        """Quick analysis of a specific path.

        Reports broken links, outbound links, and fenced blocks for the
        targeted path.
        """

        from meridian.lib.kb.graph import build_analysis
        from meridian.lib.kb.serializer import serialize_check

        try:
            resolved = validate_project_path(project_root, path)
        except PathSecurityError as exc:
            raise http_exception(status_code=403, detail=str(exc)) from exc

        if not resolved.exists():
            raise http_exception(status_code=404, detail=f"path not found: {path}")

        root = resolved if resolved.is_dir() else resolved.parent
        result = build_analysis(
            root=root,
            source_dirs=None,
            targeted_path=resolved,
            include_backlinks=False,
        )
        return serialize_check(result, resolved)

    typed_app.get("/api/kb/graph")(kb_graph)
    typed_app.get("/api/kb/check")(kb_check)


__all__ = ["register_kb_routes"]

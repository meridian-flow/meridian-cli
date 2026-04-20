"""File-related route handlers for the app server.

Exposes project files through secure, project-root-relative API endpoints:
- GET /api/files/tree — directory listing
- GET /api/files/read — file content with range support
- GET /api/files/search — fuzzy filename search
- GET /api/files/meta — file metadata
- GET /api/files/diff — unified diff
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.app.file_service import FileEntry, FileMeta, FileService
from meridian.lib.app.path_security import PathSecurityError


class _FastAPIApp(Protocol):
    """Minimal FastAPI app surface consumed by this module."""

    def get(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...


class HTTPExceptionCallable(Protocol):
    """Protocol for HTTPException constructor."""

    def __call__(
        self,
        status_code: int,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> Exception: ...


# ---- Response Models ----


class TreeEntry(BaseModel):
    """Single entry in a directory tree listing."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: str  # "file", "directory", "symlink", "other"
    size: int | None = None
    mtime: float | None = None
    git_status: str | None = None


class TreeResponse(BaseModel):
    """Response for directory tree listing."""

    model_config = ConfigDict(frozen=True)

    path: str
    entries: list[TreeEntry]


class ReadResponse(BaseModel):
    """Response for file read."""

    model_config = ConfigDict(frozen=True)

    path: str
    content: str
    total_lines: int
    start_line: int | None = None
    end_line: int | None = None


class SearchResponse(BaseModel):
    """Response for file search."""

    model_config = ConfigDict(frozen=True)

    query: str
    path_prefix: str
    results: list[str]
    truncated: bool = False


class MetaResponse(BaseModel):
    """Response for file metadata."""

    model_config = ConfigDict(frozen=True)

    path: str
    kind: str
    size: int
    mtime: float
    git_status: str | None = None
    git_history: list[str] | None = None


class DiffResponse(BaseModel):
    """Response for file diff."""

    model_config = ConfigDict(frozen=True)

    path: str
    ref_a: str
    ref_b: str | None = None
    diff: str


def _file_entry_to_tree_entry(entry: FileEntry) -> TreeEntry:
    """Convert FileEntry to TreeEntry response model."""
    return TreeEntry(
        name=entry.name,
        kind=entry.kind,
        size=entry.size,
        mtime=entry.mtime,
        git_status=entry.git_status,
    )


def _file_meta_to_response(meta: FileMeta) -> MetaResponse:
    """Convert FileMeta to MetaResponse model."""
    return MetaResponse(
        path=meta.path,
        kind=meta.kind,
        size=meta.size,
        mtime=meta.mtime,
        git_status=meta.git_status,
        git_history=meta.git_history,
    )


def register_file_routes(
    app: object,
    file_service: FileService,
    *,
    http_exception: HTTPExceptionCallable,
) -> None:
    """Register file-related routes on the FastAPI app.

    Args:
        app: FastAPI application instance
        file_service: Configured FileService instance
        http_exception: HTTPException class for error responses
    """
    from importlib import import_module

    try:
        fastapi_module = import_module("fastapi")
        Query = fastapi_module.Query
    except ModuleNotFoundError as exc:
        msg = "FastAPI is required"
        raise RuntimeError(msg) from exc

    typed_app = cast("_FastAPIApp", app)

    async def get_tree(
        path: str = Query(default=".", description="Directory path relative to project root"),
        include_hidden: bool = Query(default=False, description="Include hidden files"),
        include_git_status: bool = Query(default=False, description="Include git status"),
    ) -> TreeResponse:
        """List contents of a directory."""
        try:
            entries = file_service.list_directory(
                path,
                include_hidden=include_hidden,
                include_git_status=include_git_status,
            )
            return TreeResponse(
                path=path,
                entries=[_file_entry_to_tree_entry(e) for e in entries],
            )
        except PathSecurityError as e:
            raise http_exception(status_code=400, detail=str(e)) from e
        except FileNotFoundError as e:
            raise http_exception(status_code=404, detail=str(e)) from e
        except NotADirectoryError as e:
            raise http_exception(status_code=400, detail=str(e)) from e

    async def read_file(
        path: str = Query(..., description="File path relative to project root"),
        start_line: int | None = Query(default=None, ge=1, description="Start line (1-indexed)"),
        end_line: int | None = Query(default=None, ge=1, description="End line (1-indexed)"),
    ) -> ReadResponse:
        """Read file content with optional line range."""
        try:
            content, total_lines = file_service.read_file(
                path,
                start_line=start_line,
                end_line=end_line,
            )
            return ReadResponse(
                path=path,
                content=content,
                total_lines=total_lines,
                start_line=start_line,
                end_line=end_line,
            )
        except PathSecurityError as e:
            raise http_exception(status_code=400, detail=str(e)) from e
        except FileNotFoundError as e:
            raise http_exception(status_code=404, detail=str(e)) from e
        except IsADirectoryError as e:
            raise http_exception(status_code=400, detail=str(e)) from e
        except ValueError as e:
            raise http_exception(status_code=400, detail=str(e)) from e

    async def search_files(
        q: str = Query(..., min_length=1, description="Search query"),
        path_prefix: str = Query(default="", description="Limit search to path prefix"),
        limit: int = Query(default=50, ge=1, le=200, description="Maximum results"),
        include_hidden: bool = Query(default=False, description="Include hidden files"),
    ) -> SearchResponse:
        """Search for files by name."""
        try:
            results = file_service.search_files(
                q,
                path_prefix=path_prefix,
                max_results=limit,
                include_hidden=include_hidden,
            )
            return SearchResponse(
                query=q,
                path_prefix=path_prefix,
                results=results,
                truncated=len(results) >= limit,
            )
        except PathSecurityError as e:
            raise http_exception(status_code=400, detail=str(e)) from e

    async def get_file_meta(
        path: str = Query(..., description="File path relative to project root"),
        include_history: bool = Query(default=False, description="Include git history"),
        history_limit: int = Query(default=10, ge=1, le=100, description="Max history entries"),
    ) -> MetaResponse:
        """Get metadata for a file."""
        try:
            meta = file_service.get_file_meta(
                path,
                include_git_history=include_history,
                history_limit=history_limit,
            )
            return _file_meta_to_response(meta)
        except PathSecurityError as e:
            raise http_exception(status_code=400, detail=str(e)) from e
        except FileNotFoundError as e:
            raise http_exception(status_code=404, detail=str(e)) from e

    async def get_diff(
        path: str = Query(..., description="File path relative to project root"),
        ref_a: str = Query(default="HEAD", description="First git ref"),
        ref_b: str | None = Query(default=None, description="Second git ref (None = working tree)"),
    ) -> DiffResponse:
        """Get unified diff for a file."""
        try:
            diff = file_service.get_diff(
                path,
                ref_a=ref_a,
                ref_b=ref_b,
            )
            return DiffResponse(
                path=path,
                ref_a=ref_a,
                ref_b=ref_b,
                diff=diff,
            )
        except PathSecurityError as e:
            raise http_exception(status_code=400, detail=str(e)) from e
        except FileNotFoundError as e:
            raise http_exception(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise http_exception(status_code=400, detail=str(e)) from e
        except RuntimeError as e:
            raise http_exception(status_code=500, detail=str(e)) from e

    # Register routes
    typed_app.get("/api/files/tree")(get_tree)
    typed_app.get("/api/files/read")(read_file)
    typed_app.get("/api/files/search")(search_files)
    typed_app.get("/api/files/meta")(get_file_meta)
    typed_app.get("/api/files/diff")(get_diff)


__all__ = [
    "DiffResponse",
    "MetaResponse",
    "ReadResponse",
    "SearchResponse",
    "TreeEntry",
    "TreeResponse",
    "register_file_routes",
]

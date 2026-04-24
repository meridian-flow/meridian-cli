"""Routes for the single-spawn Meridian test chat page."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, cast


class _FastAPIApp(Protocol):
    """Minimal FastAPI route surface used by this module."""

    def get(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...


def register_test_chat_routes(
    app: object,
    *,
    session_getter: Callable[[], dict[str, object] | None],
) -> None:
    """Register the test-chat session discovery endpoint and root redirect."""

    from fastapi import HTTPException
    from fastapi.responses import RedirectResponse

    typed_app = cast("_FastAPIApp", app)

    async def get_session() -> dict[str, object]:
        session = session_getter()
        if session is None:
            raise HTTPException(status_code=503, detail="test chat session not ready")
        return session

    typed_app.get("/api/test-chat/session")(get_session)

    async def root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/test-chat.html", status_code=302)

    typed_app.get("/")(root_redirect)


__all__ = ["register_test_chat_routes"]

"""CLI command for the meridian app web UI server."""

from __future__ import annotations

import importlib
import threading
import time
import webbrowser


def run_app(
    port: int = 8420,
    no_browser: bool = False,
    host: str = "127.0.0.1",
    debug: bool = False,
    allow_unsafe_no_permissions: bool = False,
) -> None:
    """Start the Meridian app server."""

    try:
        importlib.import_module("fastapi")
        uvicorn_module = importlib.import_module("uvicorn")
    except ModuleNotFoundError:
        print("Missing app dependencies. Install with: uv sync --extra app")
        raise SystemExit(1) from None

    from meridian.lib.app.server import create_app
    from meridian.lib.ops.runtime import resolve_runtime_root_and_config, resolve_state_root
    from meridian.lib.streaming.spawn_manager import SpawnManager

    repo_root, _ = resolve_runtime_root_and_config(None)
    state_root = resolve_state_root(repo_root)

    manager = SpawnManager(state_root=state_root, repo_root=repo_root, debug=debug)
    app = create_app(
        manager,
        allow_unsafe_no_permissions=allow_unsafe_no_permissions,
    )

    if not no_browser:
        url = f"http://{host}:{port}"

        def _open_browser() -> None:
            time.sleep(1.5)
            webbrowser.open(url)

        threading.Thread(target=_open_browser, daemon=True).start()

    print(f"Starting meridian app at http://{host}:{port}")
    uvicorn_module.run(app, host=host, port=port, log_level="info")


__all__ = ["run_app"]

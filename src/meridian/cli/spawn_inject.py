"""CLI helper for injecting control messages into active streaming spawns."""

from __future__ import annotations

import asyncio
import errno
import json
import sys
from typing import cast

from meridian.lib.ops.runtime import (
    resolve_runtime_root_and_config,
    resolve_state_root,
)


def _fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


async def inject_message(
    spawn_id: str,
    message: str | None,
    *,
    interrupt: bool = False,
) -> None:
    """Send a control message to a running bidirectional spawn via Unix socket."""

    normalized_spawn_id = spawn_id.strip()
    if not normalized_spawn_id:
        _fail("spawn id is required")

    repo_root, _ = resolve_runtime_root_and_config(None)
    state_root = resolve_state_root(repo_root)
    spawn_dir = state_root / "spawns" / normalized_spawn_id
    socket_path = spawn_dir / "control.sock"

    if not spawn_dir.exists():
        _fail(f"spawn not found: {normalized_spawn_id}")

    # The control socket may not be visible immediately after spawn start.
    # Retry briefly to tolerate the startup race.
    _SOCKET_WAIT_ATTEMPTS = 3
    _SOCKET_WAIT_INTERVAL = 1.0
    for _attempt in range(_SOCKET_WAIT_ATTEMPTS):
        if socket_path.exists():
            break
        if _attempt < _SOCKET_WAIT_ATTEMPTS - 1:
            await asyncio.sleep(_SOCKET_WAIT_INTERVAL)
    else:
        _fail(f"spawn not running: {normalized_spawn_id} has no control socket")

    normalized_message = message.strip() if message is not None else ""
    action_count = int(interrupt) + int(bool(normalized_message))
    if action_count == 0:
        _fail("provide a message or --interrupt")
    if action_count > 1:
        _fail("message text is mutually exclusive with --interrupt")

    request: dict[str, str]
    if interrupt:
        request = {"type": "interrupt"}
    else:
        request = {"type": "user_message", "text": normalized_message}

    writer: asyncio.StreamWriter | None = None
    response_data = b""
    try:
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        writer.write((json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8"))
        await writer.drain()
        response_data = await asyncio.wait_for(reader.readline(), timeout=10.0)
    except TimeoutError:
        _fail(f"timed out waiting for response from spawn {normalized_spawn_id}")
    except ConnectionRefusedError:
        _fail(f"connection refused: spawn {normalized_spawn_id} is not running")
    except FileNotFoundError:
        _fail(f"spawn not running: {normalized_spawn_id} control socket disappeared")
    except OSError as exc:
        if exc.errno == errno.ENOENT:
            _fail(f"spawn not running: {normalized_spawn_id} control socket disappeared")
        if exc.errno == errno.ECONNREFUSED:
            _fail(f"connection refused: spawn {normalized_spawn_id} is not running")
        raise
    finally:
        if writer is not None:
            writer.close()
            await writer.wait_closed()

    if not response_data:
        _fail(f"spawn not running: {normalized_spawn_id} returned no response")

    parsed_obj: object | None = None
    try:
        parsed_obj = json.loads(response_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _fail(f"invalid response from spawn {normalized_spawn_id}")
    if not isinstance(parsed_obj, dict):
        _fail(f"invalid response from spawn {normalized_spawn_id}")
    parsed = cast("dict[str, object]", parsed_obj)

    ok = parsed.get("ok")
    if ok is True:
        action = "Interrupt" if interrupt else "Message"
        print(f"{action} delivered to spawn {normalized_spawn_id}")
        return

    error_value = parsed.get("error")
    if isinstance(error_value, str) and error_value.strip():
        _fail(error_value.strip())
    _fail("unknown error")

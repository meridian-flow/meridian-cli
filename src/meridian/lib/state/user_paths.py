"""User-level state root resolution and project UUID management."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from meridian.lib.platform import IS_WINDOWS
from meridian.lib.state.atomic import atomic_write_text


def get_user_state_root() -> Path:
    """Return the user-level state root directory.

    Resolution order:
    1. MERIDIAN_HOME env var if set
    2. Platform default:
       - Unix/macOS: ~/.meridian/
       - Windows: %LOCALAPPDATA%\\\\meridian\\\\
         (fallback: %USERPROFILE%\\\\AppData\\\\Local\\\\meridian\\\\)
    """

    override = os.getenv("MERIDIAN_HOME", "").strip()
    if override:
        return Path(override).expanduser()

    if IS_WINDOWS:
        local_app_data = os.getenv("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / "meridian"

        user_profile = os.getenv("USERPROFILE", "").strip()
        if user_profile:
            return Path(user_profile) / "AppData" / "Local" / "meridian"

        return Path.home() / "AppData" / "Local" / "meridian"

    return Path.home() / ".meridian"


def get_or_create_project_uuid(meridian_dir: Path) -> str:
    """Read or generate the project UUID from .meridian/id.

    - If .meridian/id exists, read and return it
    - If not, generate UUID v4, create .meridian/ and id file atomically, return UUID
    - UUID is 36 chars, no trailing newline
    """

    id_file = meridian_dir / "id"
    if id_file.is_file():
        return id_file.read_text(encoding="utf-8").strip()

    project_uuid = str(uuid.uuid4())
    meridian_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(id_file, project_uuid)
    return project_uuid


def get_project_state_root(project_uuid: str) -> Path:
    """Return the user-level project state directory.

    Returns: get_user_state_root() / "projects" / project_uuid
    """

    return get_user_state_root() / "projects" / project_uuid

"""Project root resolution helpers."""

import os
from pathlib import Path

USER_CONFIG_ENV_VAR = "MERIDIAN_CONFIG"


def resolve_project_root(explicit: Path | None = None) -> Path:
    """Resolve project root that owns Meridian project configuration.

    Precedence:
    1. Explicit function argument.
    2. `MERIDIAN_PROJECT_DIR` environment variable.
    3. Current directory / ancestors containing `.mars/`.
    4. Current directory / ancestors containing legacy `.agents/skills/`.
    5. Current working directory.
    """

    if explicit is not None:
        return explicit.expanduser().resolve()

    env_root = os.getenv("MERIDIAN_PROJECT_DIR")
    if env_root:
        return Path(env_root).expanduser().resolve()

    cwd = Path.cwd().resolve()
    candidate = cwd
    while True:
        if (candidate / ".mars").is_dir():
            return candidate

        if (candidate / ".agents" / "skills").is_dir():
            return candidate

        git_marker = candidate / ".git"
        # A .git entry (file for worktree/submodule, directory for standalone
        # repo) marks a repo boundary.
        if git_marker.exists():
            return candidate

        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent

    return cwd


def resolve_user_config_path(user_config: Path | None) -> Path | None:
    from meridian.lib.state.user_paths import get_user_home

    resolved = user_config.expanduser() if user_config is not None else None
    if resolved is None:
        raw_env = os.getenv(USER_CONFIG_ENV_VAR, "").strip()
        if raw_env:
            resolved = Path(raw_env).expanduser()

    if resolved is None:
        default_user_config = get_user_home() / "config.toml"
        try:
            if default_user_config.is_file():
                return default_user_config
        except OSError:
            import logging

            from meridian.lib.core.depth import is_nested_meridian_process

            if is_nested_meridian_process():
                logging.getLogger(__name__).warning(
                    "Implicit user config path inaccessible in nested execution: %s",
                    default_user_config,
                )
            return None
        return None

    if not resolved.is_file():
        raise FileNotFoundError(f"User Meridian config file not found: '{resolved.as_posix()}'.")
    return resolved

"""Child-process environment helpers shared by launch and spawn paths."""

from collections.abc import Callable, Collection, Mapping
from pathlib import Path
from typing import cast

from meridian.lib.harness.adapter import SpawnParams, SubprocessHarness, resolve_mcp_config
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.state.paths import resolve_work_scratch_dir
from meridian.lib.state.session_store import get_session_active_work_id

from .constants import BLOCKED_CHILD_ENV_VARS

_CHILD_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "SHELL",
        "LANG",
        "TERM",
        "TMPDIR",
        "PYTHONPATH",
        "VIRTUAL_ENV",
    }
)
_CHILD_ENV_ALLOWLIST_PREFIXES = ("LC_", "XDG_", "UV_")
_CHILD_ENV_SECRET_SUFFIXES = ("_TOKEN", "_KEY", "_SECRET")


def _is_allowlisted_child_env_var(key: str) -> bool:
    normalized = key.upper()
    if normalized in _CHILD_ENV_ALLOWLIST:
        return True
    return any(normalized.startswith(prefix) for prefix in _CHILD_ENV_ALLOWLIST_PREFIXES)


def _looks_like_secret_env_var(key: str) -> bool:
    normalized = key.upper()
    return any(normalized.endswith(suffix) for suffix in _CHILD_ENV_SECRET_SUFFIXES)


def _normalize_meridian_fs_dir(env: dict[str, str]) -> None:
    explicit_fs = env.get("MERIDIAN_FS_DIR", "").strip()
    if explicit_fs:
        env["MERIDIAN_FS_DIR"] = explicit_fs
        return

    state_root = env.get("MERIDIAN_STATE_ROOT", "").strip()
    if state_root:
        env["MERIDIAN_FS_DIR"] = (Path(state_root).expanduser() / "fs").as_posix()
        return

    repo_root = env.get("MERIDIAN_REPO_ROOT", "").strip()
    if repo_root:
        env["MERIDIAN_FS_DIR"] = (Path(repo_root).expanduser() / ".meridian" / "fs").as_posix()


def _normalize_meridian_work_dir(env: dict[str, str]) -> None:
    explicit_work = env.get("MERIDIAN_WORK_DIR", "").strip()
    if explicit_work:
        env["MERIDIAN_WORK_DIR"] = explicit_work
        return

    state_root_raw = env.get("MERIDIAN_STATE_ROOT", "").strip()
    work_id = env.get("MERIDIAN_WORK_ID", "").strip()
    if state_root_raw and work_id:
        try:
            state_root = Path(state_root_raw).expanduser()
            env["MERIDIAN_WORK_DIR"] = resolve_work_scratch_dir(state_root, work_id).as_posix()
            return
        except Exception:
            return

    chat_id = env.get("MERIDIAN_CHAT_ID", "").strip()
    if not state_root_raw or not chat_id:
        return

    try:
        state_root = Path(state_root_raw).expanduser()
        active_work_id = get_session_active_work_id(state_root, chat_id)
        if not active_work_id:
            return
        normalized_work_id = active_work_id.strip()
        if not normalized_work_id:
            return
        env["MERIDIAN_WORK_DIR"] = resolve_work_scratch_dir(
            state_root, normalized_work_id
        ).as_posix()
    except Exception:
        return


def _normalize_meridian_env(env: dict[str, str]) -> None:
    _normalize_meridian_fs_dir(env)
    _normalize_meridian_work_dir(env)


def sanitize_child_env(
    base_env: Mapping[str, str],
    env_overrides: Mapping[str, str] | None,
    pass_through: Collection[str],
) -> dict[str, str]:
    """Return a sanitized child environment with explicit pass-through controls."""

    pass_through_keys = {name.upper() for name in pass_through}
    sanitized: dict[str, str] = {}

    for key, value in base_env.items():
        normalized = key.upper()
        if _looks_like_secret_env_var(normalized) and normalized not in pass_through_keys:
            continue
        if normalized in pass_through_keys or _is_allowlisted_child_env_var(normalized):
            sanitized[key] = value

    if env_overrides is not None:
        sanitized.update(env_overrides)

    _normalize_meridian_env(sanitized)
    return sanitized


def inherit_child_env(
    base_env: Mapping[str, str],
    env_overrides: Mapping[str, str] | None,
    *,
    blocked: Collection[str] = BLOCKED_CHILD_ENV_VARS,
) -> dict[str, str]:
    """Return an inherited child environment with targeted non-propagation."""

    blocked_keys = {name.upper() for name in blocked}
    inherited = {key: value for key, value in base_env.items() if key.upper() not in blocked_keys}
    if env_overrides is not None:
        inherited.update(env_overrides)
    _normalize_meridian_env(inherited)
    return inherited


def build_harness_env_overrides(
    *,
    adapter: SubprocessHarness,
    run_params: SpawnParams,
    permission_config: PermissionConfig,
    runtime_env_overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Merge runtime + adapter + MCP env overrides for one harness launch."""

    merged: dict[str, str] = dict(runtime_env_overrides or {})
    merged.update(adapter.env_overrides(permission_config))
    mcp_config = resolve_mcp_config(adapter, run_params)
    if mcp_config is not None:
        merged.update(mcp_config.env_overrides)
    return merged


def merge_env_overrides(
    *,
    plan_overrides: Mapping[str, str],
    runtime_overrides: Mapping[str, str],
    preflight_overrides: Mapping[str, str],
) -> dict[str, str]:
    """Merge env overrides and reject `MERIDIAN_*` leaks from plan/preflight."""

    forbidden: list[tuple[str, str]] = []
    for key in plan_overrides:
        if key.startswith("MERIDIAN_"):
            forbidden.append((key, "plan_overrides"))
    for key in preflight_overrides:
        if key.startswith("MERIDIAN_"):
            forbidden.append((key, "preflight_overrides"))

    if forbidden:
        rendered = ", ".join(f"{key} via {source}" for key, source in sorted(forbidden))
        raise RuntimeError(
            "MERIDIAN_* keys may only be set by RuntimeContext.child_context(); "
            f"found leaks: {rendered}"
        )

    merged = dict(plan_overrides)
    merged.update(preflight_overrides)
    merged.update(runtime_overrides)
    return merged


def build_harness_child_env(
    *,
    base_env: Mapping[str, str],
    adapter: SubprocessHarness,
    run_params: SpawnParams,
    permission_config: PermissionConfig,
    runtime_env_overrides: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build one inherited child env for a trusted harness launch."""

    merged_env = build_harness_env_overrides(
        adapter=adapter,
        run_params=run_params,
        permission_config=permission_config,
        runtime_env_overrides=runtime_env_overrides,
    )
    blocked_child_env_vars = getattr(adapter, "blocked_child_env_vars", None)
    adapter_blocked: frozenset[str]
    if callable(blocked_child_env_vars):
        adapter_blocked = cast("Callable[[], frozenset[str]]", blocked_child_env_vars)()
    else:
        adapter_blocked = cast("frozenset[str]", frozenset())
    return inherit_child_env(
        base_env=base_env,
        env_overrides=merged_env,
        blocked=BLOCKED_CHILD_ENV_VARS | adapter_blocked,
    )

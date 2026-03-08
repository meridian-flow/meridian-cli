"""Child-process environment helpers shared by launch and spawn paths."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from pathlib import Path

from meridian.lib.harness.adapter import HarnessAdapter, SpawnParams, resolve_mcp_config
from meridian.lib.safety.permissions import PermissionConfig

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

# Harness CLIs need these credentials to authenticate. Keep this explicit so
# secret-like env vars still default to redacted unless intentionally allowed.
HARNESS_ENV_PASS_THROUGH = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_ORG_ID",
        "OPENAI_PROJECT_ID",
        "OPENAI_BASE_URL",
        "OPENROUTER_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "XAI_API_KEY",
        "MISTRAL_API_KEY",
        "COHERE_API_KEY",
        "DEEPSEEK_API_KEY",
        "TOGETHER_API_KEY",
        "PERPLEXITY_API_KEY",
    }
)


def _is_allowlisted_child_env_var(key: str) -> bool:
    normalized = key.upper()
    if normalized in _CHILD_ENV_ALLOWLIST:
        return True
    return any(normalized.startswith(prefix) for prefix in _CHILD_ENV_ALLOWLIST_PREFIXES)


def _looks_like_secret_env_var(key: str) -> bool:
    normalized = key.upper()
    return any(normalized.endswith(suffix) for suffix in _CHILD_ENV_SECRET_SUFFIXES)


def _normalize_meridian_env(env: dict[str, str]) -> None:
    space_id = env.get("MERIDIAN_SPACE_ID", "").strip()
    if not space_id:
        return

    explicit_space_fs = env.get("MERIDIAN_SPACE_FS", "").strip()
    if explicit_space_fs:
        env["MERIDIAN_SPACE_FS"] = explicit_space_fs
        return

    state_root = env.get("MERIDIAN_STATE_ROOT", "").strip()
    if state_root:
        env["MERIDIAN_SPACE_FS"] = (
            Path(state_root).expanduser() / ".spaces" / space_id / "fs"
        ).as_posix()
        return

    repo_root = env.get("MERIDIAN_REPO_ROOT", "").strip()
    if repo_root:
        env["MERIDIAN_SPACE_FS"] = (
            Path(repo_root).expanduser() / ".meridian" / ".spaces" / space_id / "fs"
        ).as_posix()


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


def build_harness_env_overrides(
    *,
    adapter: HarnessAdapter,
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


def build_harness_child_env(
    *,
    base_env: Mapping[str, str],
    adapter: HarnessAdapter,
    run_params: SpawnParams,
    permission_config: PermissionConfig,
    runtime_env_overrides: Mapping[str, str] | None = None,
    pass_through: Collection[str] = HARNESS_ENV_PASS_THROUGH,
) -> dict[str, str]:
    """Build one sanitized child env for a harness launch."""

    merged_env = build_harness_env_overrides(
        adapter=adapter,
        run_params=run_params,
        permission_config=permission_config,
        runtime_env_overrides=runtime_env_overrides,
    )
    return sanitize_child_env(
        base_env=base_env,
        env_overrides=merged_env,
        pass_through=pass_through,
    )

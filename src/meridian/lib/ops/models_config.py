"""CLI-facing operations for `.meridian/models.toml`."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.catalog.models_toml import ensure_models_config, render_models_toml
from meridian.lib.config.settings import resolve_repo_root
from meridian.lib.core.util import FormatContext, to_jsonable
from meridian.lib.ops.runtime import async_from_sync
from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.paths import resolve_state_paths

_MODELS_VISIBILITY_KEYS = frozenset({
    "include", "exclude", "max_input_cost", "max_age_days",
    "hide_date_variants", "hide_superseded",
})
_MODELS_ENTRY_KEYS = frozenset({
    "model_id", "id", "description", "pinned",
    "provider", "include", "exclude",
})


class ModelsConfigInitInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_root: str | None = None


class ModelsConfigInitOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    created: bool

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        return f"{'created' if self.created else 'exists'}: {self.path}"


class ModelsConfigShowInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_root: str | None = None


class ModelsConfigShowOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    content: str

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        return f"path: {self.path}\n{self.content}".rstrip()


class ModelsConfigGetInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    repo_root: str | None = None


class ModelsConfigGetOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    value: object | None
    found: bool

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        if not self.found:
            return f"{self.key}: (unset)"
        return f"{self.key}: {to_jsonable(self.value)}"


class ModelsConfigSetInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    value: str
    repo_root: str | None = None


class ModelsConfigSetOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    key: str
    value: object

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        return f"set {self.key} = {to_jsonable(self.value)} in {self.path}"


class ModelsConfigResetInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    repo_root: str | None = None


class ModelsConfigResetOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    key: str
    removed: bool

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        status = "removed" if self.removed else "already-default"
        return f"reset {self.key} ({status}) in {self.path}"


def _resolve_repo_root(repo_root: str | None) -> Path:
    explicit = Path(repo_root).expanduser().resolve() if repo_root else None
    return resolve_repo_root(explicit)


def _config_path(repo_root: Path) -> Path:
    return resolve_state_paths(repo_root).models_path


def _load_payload(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    raw_text = path.read_text(encoding="utf-8")
    if not raw_text.strip():
        return {}
    payload = tomllib.loads(raw_text)
    return cast("dict[str, object]", payload)


def _parse_toml_literal(raw_value: str) -> object:
    try:
        payload = tomllib.loads(f"value = {raw_value}")
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML literal: {raw_value!r}") from exc
    return cast("dict[str, object]", payload)["value"]


def _validated_key_parts(key: str) -> tuple[str, ...]:
    parts = tuple(part.strip() for part in key.split(".") if part.strip())
    if not parts:
        raise ValueError("Config key must not be empty.")

    root = parts[0]
    if root == "models" and len(parts) == 2:
        return parts
    if root == "models" and len(parts) == 3 and parts[2] in _MODELS_ENTRY_KEYS:
        return parts
    if root == "model_visibility" and len(parts) == 2 and parts[1] in _MODELS_VISIBILITY_KEYS:
        return parts

    raise ValueError(
        "Unsupported models config key. Use models.<name>, "
        "models.<name>.{description|pinned|model_id|provider|include|exclude}, "
        "or model_visibility."
        "{include|exclude|max_input_cost|max_age_days|hide_date_variants|hide_superseded}."
    )


def _validate_value(parts: tuple[str, ...], value: object) -> object:
    root = parts[0]
    if root == "models":
        if len(parts) == 2:
            # models.<name> = "model-id" (shorthand string alias)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("models.<name> expects a non-empty string model id.")
            return value.strip()
        # models.<name>.<field>
        field = parts[2]
        if field in {"model_id", "id", "description"}:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"models.<name>.{field} expects a non-empty string.")
            return value.strip()
        if field == "pinned":
            if not isinstance(value, bool):
                raise ValueError("models.<name>.pinned expects true or false.")
            return value
        if field == "provider":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("models.<name>.provider expects a non-empty string.")
            return value.strip()
        if field == "include":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("models.<name>.include expects a non-empty string.")
            return value.strip()
        if field == "exclude":
            if not isinstance(value, list):
                raise ValueError("models.<name>.exclude expects an array of strings.")
            patterns: list[str] = []
            for item in cast("list[object]", value):
                if not isinstance(item, str) or not item.strip():
                    raise ValueError("models.<name>.exclude expects an array of strings.")
                patterns.append(item.strip())
            return patterns
        raise ValueError(f"Unsupported config key: {'.'.join(parts)}.")

    if parts[1] in {"include", "exclude"}:
        if not isinstance(value, list):
            raise ValueError(f"{'.'.join(parts)} expects an array of strings.")
        patterns = []
        for item in cast("list[object]", value):
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"{'.'.join(parts)} expects an array of strings.")
            patterns.append(item.strip())
        return patterns
    if parts[1] in {"hide_date_variants", "hide_superseded"}:
        if not isinstance(value, bool):
            raise ValueError(f"model_visibility.{parts[1]} expects true or false.")
        return value
    if parts[1] == "max_age_days":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("model_visibility.max_age_days expects an int.")
        return value
    if parts[1] == "max_input_cost":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("model_visibility.max_input_cost expects a float.")
        return float(value)

    raise ValueError(f"Unsupported config key: {'.'.join(parts)}.")


def _assign_nested_value(payload: dict[str, object], parts: tuple[str, ...], value: object) -> None:
    current = payload
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            replacement: dict[str, object] = {}
            current[part] = replacement
            current = replacement
            continue
        current = cast("dict[str, object]", nested)
    current[parts[-1]] = value


def _get_nested_value(
    payload: dict[str, object],
    parts: tuple[str, ...],
) -> tuple[bool, object | None]:
    current_dict: dict[str, object] = payload
    current_value: object | None = None
    for index, part in enumerate(parts):
        if part not in current_dict:
            return False, None
        current_value = current_dict[part]
        if index == len(parts) - 1:
            return True, current_value
        if not isinstance(current_value, dict):
            return False, None
        current_dict = cast("dict[str, object]", current_value)
    return False, None


def _remove_nested_value(payload: dict[str, object], parts: tuple[str, ...]) -> bool:
    current = payload
    parents: list[tuple[dict[str, object], str]] = []
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            return False
        parents.append((current, part))
        current = cast("dict[str, object]", nested)

    if parts[-1] not in current:
        return False
    current.pop(parts[-1], None)

    while parents:
        parent, key = parents.pop()
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            parent.pop(key, None)
            continue
        break
    return True


def models_config_init_sync(payload: ModelsConfigInitInput) -> ModelsConfigInitOutput:
    repo_root = _resolve_repo_root(payload.repo_root)
    path = _config_path(repo_root)
    created = not path.exists()
    ensure_models_config(repo_root)
    return ModelsConfigInitOutput(path=path.as_posix(), created=created)


def models_config_show_sync(payload: ModelsConfigShowInput) -> ModelsConfigShowOutput:
    repo_root = _resolve_repo_root(payload.repo_root)
    path = _config_path(repo_root)
    ensure_models_config(repo_root)
    return ModelsConfigShowOutput(path=path.as_posix(), content=path.read_text(encoding="utf-8"))


def models_config_get_sync(payload: ModelsConfigGetInput) -> ModelsConfigGetOutput:
    repo_root = _resolve_repo_root(payload.repo_root)
    path = _config_path(repo_root)
    ensure_models_config(repo_root)
    parts = _validated_key_parts(payload.key)
    found, value = _get_nested_value(_load_payload(path), parts)
    return ModelsConfigGetOutput(key=".".join(parts), value=value, found=found)


def models_config_set_sync(payload: ModelsConfigSetInput) -> ModelsConfigSetOutput:
    repo_root = _resolve_repo_root(payload.repo_root)
    path = _config_path(repo_root)
    ensure_models_config(repo_root)
    parts = _validated_key_parts(payload.key)
    value = _validate_value(parts, _parse_toml_literal(payload.value))

    file_payload = _load_payload(path)
    _assign_nested_value(file_payload, parts, value)
    atomic_write_text(path, render_models_toml(file_payload))
    return ModelsConfigSetOutput(path=path.as_posix(), key=".".join(parts), value=value)


def models_config_reset_sync(payload: ModelsConfigResetInput) -> ModelsConfigResetOutput:
    repo_root = _resolve_repo_root(payload.repo_root)
    path = _config_path(repo_root)
    ensure_models_config(repo_root)
    parts = _validated_key_parts(payload.key)

    file_payload = _load_payload(path)
    removed = _remove_nested_value(file_payload, parts)
    atomic_write_text(path, render_models_toml(file_payload))
    return ModelsConfigResetOutput(path=path.as_posix(), key=".".join(parts), removed=removed)


models_config_init = async_from_sync(models_config_init_sync)
models_config_show = async_from_sync(models_config_show_sync)
models_config_get = async_from_sync(models_config_get_sync)
models_config_set = async_from_sync(models_config_set_sync)
models_config_reset = async_from_sync(models_config_reset_sync)

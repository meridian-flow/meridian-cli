"""Runtime context derived from MERIDIAN_* environment variables."""

from contextlib import suppress
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.types import SpawnId
from meridian.lib.state.paths import resolve_repo_state_paths, resolve_work_scratch_dir


class RuntimeContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: SpawnId | None = None
    depth: int = 0
    repo_root: Path | None = None
    state_root: Path | None = None
    chat_id: str = ""
    work_id: str | None = None

    @classmethod
    def from_environment(cls) -> Self:
        """Build context from MERIDIAN_* environment variables."""

        import os

        spawn_id_raw = os.getenv("MERIDIAN_SPAWN_ID", "").strip()
        depth_raw = os.getenv("MERIDIAN_DEPTH", "0").strip()
        repo_root_raw = os.getenv("MERIDIAN_REPO_ROOT", "").strip()
        state_root_raw = os.getenv("MERIDIAN_STATE_ROOT", "").strip()
        chat_id_raw = os.getenv("MERIDIAN_CHAT_ID", "").strip()
        work_id_raw = os.getenv("MERIDIAN_WORK_ID", "").strip()

        depth = 0
        with suppress(ValueError, TypeError):
            depth = max(0, int(depth_raw))

        return cls(
            spawn_id=SpawnId(spawn_id_raw) if spawn_id_raw else None,
            depth=depth,
            repo_root=Path(repo_root_raw) if repo_root_raw else None,
            state_root=Path(state_root_raw) if state_root_raw else None,
            chat_id=chat_id_raw,
            work_id=work_id_raw or None,
        )

    def to_env_overrides(self) -> dict[str, str]:
        """Produce MERIDIAN_* env overrides for child processes."""

        overrides: dict[str, str] = {"MERIDIAN_DEPTH": str(self.depth)}
        if self.spawn_id is not None:
            overrides["MERIDIAN_SPAWN_ID"] = str(self.spawn_id)
        if self.repo_root is not None:
            overrides["MERIDIAN_REPO_ROOT"] = self.repo_root.as_posix()
        if self.state_root is not None:
            overrides["MERIDIAN_STATE_ROOT"] = self.state_root.as_posix()
        if self.chat_id:
            overrides["MERIDIAN_CHAT_ID"] = self.chat_id
        if self.work_id:
            overrides["MERIDIAN_WORK_ID"] = self.work_id
            if self.repo_root is not None:
                overrides["MERIDIAN_WORK_DIR"] = resolve_work_scratch_dir(
                    resolve_repo_state_paths(self.repo_root).root_dir,
                    self.work_id,
                ).as_posix()
            elif self.state_root is not None:
                overrides["MERIDIAN_WORK_DIR"] = resolve_work_scratch_dir(
                    self.state_root,
                    self.work_id,
                ).as_posix()
        return overrides

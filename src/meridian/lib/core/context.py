"""Runtime context derived from MERIDIAN_* environment variables."""

from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.resolved_context import ResolvedContext
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
        resolved = ResolvedContext.from_environment()

        return cls(
            spawn_id=resolved.spawn_id,
            depth=resolved.depth,
            repo_root=resolved.repo_root,
            state_root=resolved.state_root,
            chat_id=resolved.chat_id,
            work_id=resolved.work_id,
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

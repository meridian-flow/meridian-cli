"""SKILL.md parsing, scanning, and filesystem-backed skill catalog."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.config.settings import bundled_agents_root, resolve_path_list, resolve_repo_root
from meridian.lib.config.settings import SearchPathConfig, load_config
from meridian.lib.core.domain import IndexReport, SkillContent, SkillManifest

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


# ---------------------------------------------------------------------------
# Skill document model
# ---------------------------------------------------------------------------


class SkillDocument(BaseModel):
    """Parsed representation of one SKILL.md file."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    tags: tuple[str, ...]
    path: Path
    content: str
    body: str
    frontmatter: dict[str, object]


# ---------------------------------------------------------------------------
# Markdown frontmatter parsing
# ---------------------------------------------------------------------------


def split_markdown_frontmatter(markdown: str) -> tuple[dict[str, object], str]:
    """Split markdown into YAML frontmatter and body."""
    import frontmatter  # type: ignore[import-untyped]
    import yaml

    try:
        post = frontmatter.loads(markdown)
    except yaml.YAMLError:
        logger.warning("Malformed YAML frontmatter, treating as plain markdown")
        return {}, markdown
    return dict(post.metadata), post.content


def _coerce_string_list(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        candidate = value.strip()
        return (candidate,) if candidate else ()
    if isinstance(value, list):
        normalized = [
            str(item).strip()
            for item in cast("list[object]", value)
            if str(item).strip()
        ]
        return tuple(normalized)
    return ()


# ---------------------------------------------------------------------------
# Skill file parsing and discovery
# ---------------------------------------------------------------------------


def parse_skill_file(path: Path) -> SkillDocument:
    """Parse one SKILL.md file."""

    content = path.read_text(encoding="utf-8")
    frontmatter, body = split_markdown_frontmatter(content)

    name_value = frontmatter.get("name")
    description_value = frontmatter.get("description")
    tags_value = frontmatter.get("tags")

    name = str(name_value).strip() if name_value is not None else path.parent.name
    description = str(description_value).strip() if description_value is not None else ""
    tags = _coerce_string_list(tags_value)

    return SkillDocument(
        name=name or path.parent.name,
        description=description,
        tags=tags,
        path=path.resolve(),
        content=content,
        body=body,
        frontmatter=frontmatter,
    )


def discover_skill_files(skills_dir: Path) -> list[Path]:
    """Discover all SKILL.md files under `.agents/skills/`."""

    if not skills_dir.is_dir():
        return []
    return sorted(path for path in skills_dir.rglob("SKILL.md") if path.is_file())


def _skill_search_dirs(repo_root: Path) -> list[Path]:
    config = load_config(repo_root).search_paths
    return resolve_path_list(
        config.skills,
        config.global_skills,
        repo_root,
    )


def _files_have_equal_text(first: Path, second: Path) -> bool:
    try:
        return first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    except OSError:
        return False


def scan_skills(
    repo_root: Path | None = None,
    skills_dirs: list[Path] | None = None,
) -> list[SkillDocument]:
    """Scan configured skill directories and parse all discovered skills."""

    root = resolve_repo_root(repo_root)
    directories = skills_dirs if skills_dirs is not None else _skill_search_dirs(root)
    documents: list[SkillDocument] = []
    selected_by_name: dict[str, SkillDocument] = {}

    for directory in directories:
        for path in discover_skill_files(directory):
            document = parse_skill_file(path)
            existing = selected_by_name.get(document.name)
            if existing is not None:
                if _files_have_equal_text(existing.path, document.path):
                    continue
                logger.warning(
                    "Skill '%s' found in multiple paths with conflicting content: %s, %s. "
                    "Using %s; conflicting duplicate ignored.",
                    document.name,
                    existing.path,
                    document.path,
                    existing.path,
                )
                continue
            selected_by_name[document.name] = document
            documents.append(document)
    return documents


# ---------------------------------------------------------------------------
# Skill registry
# ---------------------------------------------------------------------------


class SkillRegistry:
    """Skill catalog with discovery from configured skill directories."""

    def __init__(
        self,
        db_path: Path | None = None,
        repo_root: Path | None = None,
        *,
        busy_timeout_ms: int = 0,
        search_paths: SearchPathConfig | None = None,
        readonly: bool = False,
    ) -> None:
        _ = db_path
        _ = busy_timeout_ms
        self._repo_root = resolve_repo_root(repo_root)
        resolved_search_paths = search_paths or load_config(self._repo_root).search_paths
        resolved_skills_dirs = resolve_path_list(
            resolved_search_paths.skills,
            resolved_search_paths.global_skills,
            self._repo_root,
        )
        bundled_root = bundled_agents_root()
        if bundled_root is not None:
            bundled_skills_dir = bundled_root / "skills"
            if bundled_skills_dir.is_dir() and bundled_skills_dir not in resolved_skills_dirs:
                resolved_skills_dirs.append(bundled_skills_dir)

        self._skills_dirs = tuple(resolved_skills_dirs)
        self._readonly = readonly
        self._filesystem_documents: tuple[SkillDocument, ...] | None = None

    @property
    def repo_root(self) -> Path:
        return self._repo_root

    @property
    def skills_dirs(self) -> tuple[Path, ...]:
        return self._skills_dirs

    @property
    def readonly(self) -> bool:
        return self._readonly

    @property
    def db_path(self) -> Path:
        return self._repo_root / ".meridian" / "index" / "skills.json"

    def _scan_documents(self, *, refresh: bool = False) -> tuple[SkillDocument, ...]:
        if self._filesystem_documents is None or refresh:
            self._filesystem_documents = tuple(
                scan_skills(self._repo_root, skills_dirs=list(self._skills_dirs))
            )
        return self._filesystem_documents

    def reindex(self, skills_dir: Path | None = None) -> IndexReport:
        """Refresh in-memory index from configured skill search directories."""

        scan_dirs: list[Path]
        if skills_dir is not None:
            requested = skills_dir.resolve()
            if requested not in self._skills_dirs:
                expected = ", ".join(path.as_posix() for path in self._skills_dirs)
                expected_text = expected if expected else "<none>"
                raise ValueError(
                    "Skill discovery is restricted to configured search paths; "
                    f"expected one of '{expected_text}', got '{skills_dir}'."
                )
            scan_dirs = [requested]
        else:
            scan_dirs = list(self._skills_dirs)

        documents = tuple(scan_skills(self._repo_root, skills_dirs=scan_dirs))
        self._filesystem_documents = documents
        return IndexReport(indexed_count=len(documents))

    def list(self) -> list[SkillManifest]:
        """List all discovered skills."""

        return sorted(
            [
                SkillManifest(
                    name=document.name,
                    description=document.description,
                    tags=document.tags,
                    path=str(document.path),
                )
                for document in self._scan_documents()
            ],
            key=lambda item: item.name,
        )

    def search(self, query: str) -> list[SkillManifest]:
        """Keyword search against name/description/tags/content."""

        normalized = query.strip().lower()
        if not normalized:
            return self.list()

        return sorted(
            [
                SkillManifest(
                    name=document.name,
                    description=document.description,
                    tags=document.tags,
                    path=str(document.path),
                )
                for document in self._scan_documents()
                if normalized in document.name.lower()
                or normalized in document.description.lower()
                or normalized in " ".join(document.tags).lower()
                or normalized in document.content.lower()
            ],
            key=lambda item: item.name,
        )

    def load(self, names: list[str]) -> list[SkillContent]:
        """Load full SKILL.md content for specific skill names in requested order."""

        normalized_names = [name.strip() for name in names if name.strip()]
        if not normalized_names:
            return []

        docs_by_name = {document.name: document for document in self._scan_documents()}
        missing = [name for name in normalized_names if name not in docs_by_name]
        if missing:
            raise KeyError(f"Unknown skills: {', '.join(missing)}")

        return [
            SkillContent(
                name=docs_by_name[name].name,
                description=docs_by_name[name].description,
                tags=docs_by_name[name].tags,
                content=docs_by_name[name].content,
                path=str(docs_by_name[name].path),
            )
            for name in normalized_names
        ]

    def show(self, name: str) -> SkillContent:
        """Load one skill content payload by name."""

        loaded = self.load([name])
        return loaded[0]

from __future__ import annotations

from importlib.resources import files

import meridian

_RESOURCE_PATHS = (
    ".agents/agents/agent.md",
    ".agents/agents/primary.md",
    ".agents/skills/orchestrate-meridian/SKILL.md",
    ".agents/skills/spawn-agent-meridian/SKILL.md",
)


def main() -> None:
    if not meridian.__version__:
        raise SystemExit("meridian.__version__ must not be empty")

    resources = files("meridian.resources")
    for relative_path in _RESOURCE_PATHS:
        resource = resources.joinpath(relative_path)
        if not resource.is_file():
            raise SystemExit(f"missing bundled resource: {relative_path}")


if __name__ == "__main__":
    main()

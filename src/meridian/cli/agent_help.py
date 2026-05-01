"""Agent-mode help supplements for CLI subcommands."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cyclopts import App

_SPAWN_SUPPLEMENT = (
    "Agent Notes:\n\n"
    "Lifecycle: queued → running → finalizing → succeeded | failed | cancelled.\n"
    "'finalizing' is transient — treat as active when polling.\n\n"
    "Which subcommand when:\n\n"
    "  show ID        Status, report, cost — first check for any spawn\n\n"
    "  wait [ID]      Block until spawn(s) reach terminal state\n\n"
    "  list           Active spawns (--all for recent history)\n\n"
    "  children ID    What a spawn delegated to\n\n"
    "  files ID       List changed paths for staging or review\n\n"
    "  inject ID      Course-correct a running spawn before cancelling\n\n"
    "  cancel ID      Stop a spawn when correction is no longer useful\n\n"
    "Transcripts: 'meridian session log ID'.\n"
)

_SESSION_SUPPLEMENT = (
    "Agent Notes:\n\n"
    "Omitting REF defaults to the top-level primary session at every depth.\n"
    "Pass an explicit spawn id to inspect a specific spawn's transcript.\n\n"
    "Which subcommand when:\n\n"
    "  log REF            Read a transcript\n\n"
    "  log REF -c 0       Latest compacted segment; increment -c for older\n\n"
    "  log --file PATH    Read a session file directly\n\n"
    "  search QUERY REF   Case-insensitive search across segments\n\n"
    "REF forms: chat id (c123), spawn id (p123), or harness session id.\n\n"
    "Decision recovery: 'meridian work sessions WORK_ID --all'\n"
)

_CONFIG_SUPPLEMENT = (
    "Agent Notes:\n\n"
    "Resolution is per field:\n"
    "CLI flag > env var > profile > project > user > harness default\n\n"
    "A CLI model override (-m) also drives harness routing.\n\n"
    "Quick reference:\n\n"
    "  config show            All resolved values with sources\n\n"
    "  config get KEY         One key with source\n\n"
    "  config set KEY VALUE   Set in meridian.toml\n\n"
    "  config init            Scaffold with commented defaults\n"
)

_WORK_SUPPLEMENT = (
    "Agent Notes:\n\n"
    "Dashboard: 'meridian work' shows active work items with their spawns.\n\n"
    "Quick reference:\n\n"
    "  work start LABEL       Create or switch to a work item\n\n"
    "  work current           Print active work item directory path\n\n"
    "  work done WORK_ID      Mark done and archive scratch directory\n\n"
    "  work sessions WORK_ID  Sessions tied to this item (--all for archived)\n\n"
    "Artifact placement: $MERIDIAN_WORK_DIR for this item,\n"
    "$MERIDIAN_CONTEXT_KB_DIR for project-wide knowledge.\n"
)

_DOCTOR_SUPPLEMENT = (
    "Agent Notes:\n\n"
    "Run when a spawn seems stuck or status doesn't match reality.\n"
    "Spawn read paths (show, list, wait) and 'doctor' reconcile orphans.\n\n"
    "Common failure modes:\n\n"
    "  orphan_run              Runner died mid-flight. Relaunch.\n\n"
    "  orphan_finalization     Exited without finalizing. Check 'spawn show'\n"
    "                          for partial report.\n\n"
    "  Exit 127 / empty report Harness binary missing from PATH.\n\n"
    "  Exit 143 or 137         Check 'spawn show' first — if already\n"
    "                          succeeded, signal hit during cleanup.\n"
    "                          Otherwise retry.\n\n"
    "For the transcript: 'meridian session log SPAWN_ID'.\n"
)

AGENT_HELP_SUPPLEMENTS: dict[str, str] = {
    "spawn": _SPAWN_SUPPLEMENT,
    "session": _SESSION_SUPPLEMENT,
    "config": _CONFIG_SUPPLEMENT,
    "work": _WORK_SUPPLEMENT,
    "doctor": _DOCTOR_SUPPLEMENT,
}

_ORIGINAL_EPILOGUES: dict[str, str | None] = {}


def _agent_help_apps() -> dict[str, App]:
    from cyclopts import App

    from meridian.cli.app_tree import app

    commands = getattr(app, "_commands", {})
    return {
        name: app_obj
        for name in AGENT_HELP_SUPPLEMENTS
        if isinstance((app_obj := commands.get(name)), App)
    }


def apply_agent_help_supplements() -> None:
    """Mutate App help_epilogue to include agent supplements when in agent mode."""

    if _ORIGINAL_EPILOGUES:
        return

    for name, app_obj in _agent_help_apps().items():
        if name not in _ORIGINAL_EPILOGUES:
            _ORIGINAL_EPILOGUES[name] = app_obj.help_epilogue
        supplement = AGENT_HELP_SUPPLEMENTS.get(name)
        if supplement is None:
            continue
        existing = app_obj.help_epilogue or ""
        if existing and not existing.endswith("\n"):
            existing += "\n"
        app_obj.help_epilogue = existing + "\n" + supplement


def restore_help_supplements() -> None:
    """Restore App help_epilogue values captured before agent supplements."""

    apps = _agent_help_apps()
    for name, original in _ORIGINAL_EPILOGUES.items():
        app_obj = apps.get(name)
        if app_obj is not None:
            app_obj.help_epilogue = original
    _ORIGINAL_EPILOGUES.clear()

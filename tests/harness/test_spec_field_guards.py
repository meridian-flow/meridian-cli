"""Cross-adapter SpawnParams accounting guard tests."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace

import pytest

from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.ids import HarnessId
from meridian.lib.harness.launch_spec import _enforce_spawn_params_accounting

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _scan_files_for_pattern(
    roots: Iterable[str | Path],
    pattern: str,
    *,
    suffixes: tuple[str, ...] = (".py",),
) -> list[tuple[Path, int, str]]:
    """Return (path, lineno, line) for every matching line under roots."""
    compiled = re.compile(pattern)
    matches: list[tuple[Path, int, str]] = []
    for root in roots:
        root_path = Path(root)
        if root_path.is_file():
            files = [root_path]
        else:
            files = [p for p in root_path.rglob("*") if p.is_file() and p.suffix in suffixes]
        for file_path in files:
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if compiled.search(line):
                    matches.append((file_path, lineno, line))
    return matches


def test_enforce_spawn_params_accounting_reports_missing_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_fields = dict(SpawnParams.model_fields)
    patched_fields = dict(original_fields)
    patched_fields["bogus_phase2_field"] = object()
    monkeypatch.setattr(SpawnParams, "model_fields", patched_fields)

    fake_registry = {
        HarnessId.CLAUDE: SimpleNamespace(
            adapter=SimpleNamespace(handled_fields=frozenset(original_fields))
        )
    }

    with pytest.raises(ImportError, match="bogus_phase2_field"):
        _enforce_spawn_params_accounting(registry=fake_registry)


def test_launch_spec_guard_uses_no_runtime_asserts() -> None:
    launch_spec_path = Path("src/meridian/lib/harness/launch_spec.py")
    matches = _scan_files_for_pattern(
        [_REPO_ROOT / launch_spec_path],
        r"^\s*assert\s",
    )
    assert not matches, f"Found matches: {matches}"


@pytest.mark.parametrize("python_optimize", ("0", "1"))
def test_launch_spec_import_is_clean_in_unmodified_tree(python_optimize: str) -> None:
    env = dict(os.environ)
    env["PYTHONOPTIMIZE"] = python_optimize
    result = subprocess.run(
        [sys.executable, "-c", "import meridian.lib.harness.launch_spec"],
        capture_output=True,
        check=False,
        cwd=_REPO_ROOT,
        env=env,
        text=True,
    )
    assert result.returncode == 0, result.stderr

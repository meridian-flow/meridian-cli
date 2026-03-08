"""Shared pytest fixtures."""


import os
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def package_root() -> Path:
    return PACKAGE_ROOT


@pytest.fixture(autouse=True)
def _clean_meridian_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate tests from parent harness runtime state environment."""

    for key in tuple(os.environ):
        if key.startswith("MERIDIAN_"):
            monkeypatch.delenv(key, raising=False)

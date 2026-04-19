"""Unit tests for Mars operation helpers."""

import json
import subprocess
from pathlib import Path

import pytest

from meridian.lib.ops import mars


def _patch_outdated_command(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload: list[object] | None = None,
    returncode: int = 0,
    stdout: str | None = None,
) -> list[list[str]]:
    monkeypatch.setattr(mars, "resolve_mars_executable", lambda: "/usr/bin/mars")
    observed: list[list[str]] = []

    def _fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        observed.append(cmd)
        output = stdout if stdout is not None else json.dumps(payload if payload is not None else [])
        return subprocess.CompletedProcess(args=cmd, returncode=returncode, stdout=output, stderr="")

    monkeypatch.setattr(mars.subprocess, "run", _fake_run)
    return observed


def test_check_upgrade_availability_handles_mixed_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_outdated_command(
        monkeypatch,
        payload=[
            {
                "source": "within",
                "locked": "v1.0.0",
                "constraint": "^1",
                "updateable": "v1.1.0",
                "latest": "v2.0.0",
            },
            {
                "source": "beyond",
                "locked": "v0.0.11",
                "constraint": "v0.0.11",
                "updateable": "v0.0.11",
                "latest": "v0.0.12",
            },
            {
                "source": "up-to-date",
                "locked": "v2.0.0",
                "constraint": "^2",
                "updateable": "v2.0.0",
                "latest": "v2.0.0",
            },
            {
                "source": "head-only",
                "locked": "abc",
                "constraint": "HEAD",
                "updateable": "def",
                "latest": "def",
            },
            {
                "source": "within",
                "locked": "v1.0.0",
                "constraint": "^1",
                "updateable": "v1.1.0",
                "latest": "v2.0.0",
            },
        ],
    )

    availability = mars.check_upgrade_availability()

    assert availability == mars.UpgradeAvailability(
        within_constraint=("within",),
        beyond_constraint=("beyond",),
    )


def test_check_upgrade_availability_passes_root_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed = _patch_outdated_command(monkeypatch)

    availability = mars.check_upgrade_availability(tmp_path)

    assert availability == mars.UpgradeAvailability()
    assert observed == [
        ["/usr/bin/mars", "outdated", "--json", "--root", tmp_path.as_posix()]
    ]


@pytest.mark.parametrize("failure_case", ["no_binary", "nonzero_exit", "invalid_json"])
def test_check_upgrade_availability_returns_none_on_failures(
    monkeypatch: pytest.MonkeyPatch,
    failure_case: str,
) -> None:
    if failure_case == "no_binary":
        monkeypatch.setattr(mars, "resolve_mars_executable", lambda: None)
    elif failure_case == "nonzero_exit":
        _patch_outdated_command(monkeypatch, returncode=2, payload=[])
    else:
        _patch_outdated_command(monkeypatch, stdout="{not-json}")

    assert mars.check_upgrade_availability() is None


@pytest.mark.parametrize(
    ("row", "description"),
    [
        (
            {
                "source": "missing-latest",
                "locked": "v1.0.0",
                "constraint": "^1",
                "updateable": "v1.1.0",
            },
            "missing latest",
        ),
        (
            {
                "source": "blank-latest",
                "locked": "v1.0.0",
                "constraint": "^1",
                "updateable": "v1.1.0",
                "latest": " ",
            },
            "blank latest",
        ),
        (
            {
                "source": "blank-locked",
                "locked": "",
                "constraint": "^1",
                "updateable": "v1.1.0",
                "latest": "v1.2.0",
            },
            "blank locked",
        ),
        (
            {
                "source": "blank-updateable",
                "locked": "v1.0.0",
                "constraint": "^1",
                "updateable": " ",
                "latest": "v1.2.0",
            },
            "blank updateable",
        ),
    ],
)
def test_check_upgrade_availability_skips_malformed_rows(
    monkeypatch: pytest.MonkeyPatch,
    row: dict[str, str],
    description: str,
) -> None:
    del description
    _patch_outdated_command(
        monkeypatch,
        payload=[
            row,
            {
                "source": "valid",
                "locked": "v0.2.0",
                "constraint": "^0.2",
                "updateable": "v0.2.1",
                "latest": "v0.3.0",
            },
        ],
    )

    availability = mars.check_upgrade_availability()

    assert availability == mars.UpgradeAvailability(
        within_constraint=("valid",),
        beyond_constraint=(),
    )


@pytest.mark.parametrize(
    ("availability", "style", "expected"),
    [
        (mars.UpgradeAvailability(), "hint", ()),
        (
            mars.UpgradeAvailability(within_constraint=("meridian-base",)),
            "hint",
            (
                "hint: 1 update available within your pinned constraint: meridian-base.",
                "      Run `meridian mars upgrade` to apply.",
            ),
        ),
        (
            mars.UpgradeAvailability(beyond_constraint=("meridian-base",)),
            "hint",
            (
                "hint: 1 newer version available beyond your pinned constraint: meridian-base.",
                "      Edit mars.toml to bump the version, then run `meridian mars sync`.",
            ),
        ),
        (
            mars.UpgradeAvailability(
                within_constraint=("foo", "bar"),
                beyond_constraint=("meridian-base",),
            ),
            "hint",
            (
                "hint: 2 updates available within your pinned constraint: foo, bar.",
                "      Run `meridian mars upgrade` to apply.",
                "      1 newer version available beyond your pinned constraint: meridian-base.",
                "      Edit mars.toml to bump the version, then run `meridian mars sync`.",
            ),
        ),
        (
            mars.UpgradeAvailability(
                within_constraint=("foo",),
                beyond_constraint=("meridian-base",),
            ),
            "warning",
            (
                "1 update available within your pinned constraint: foo.",
                "      Run `meridian mars upgrade` to apply.",
                "      1 newer version available beyond your pinned constraint: meridian-base.",
                "      Edit mars.toml to bump the version, then run `meridian mars sync`.",
            ),
        ),
    ],
)
def test_format_upgrade_availability(
    availability: mars.UpgradeAvailability,
    style: str,
    expected: tuple[str, ...],
) -> None:
    assert mars.format_upgrade_availability(availability, style=style) == expected

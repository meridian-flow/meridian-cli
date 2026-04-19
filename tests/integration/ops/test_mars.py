"""Tests for Mars operation helpers."""

import json
import subprocess
from pathlib import Path

import pytest

from meridian.lib.ops import mars


def _patch_outdated_payload(
    monkeypatch: pytest.MonkeyPatch,
    payload: list[object],
) -> None:
    monkeypatch.setattr(mars, "resolve_mars_executable", lambda: "/usr/bin/mars")

    def _fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["/usr/bin/mars", "outdated", "--json"],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(mars.subprocess, "run", _fake_run)


def test_check_upgrade_availability_classifies_exact_pin_as_beyond_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_outdated_payload(
        monkeypatch,
        [
            {
                "source": "meridian-base",
                "locked": "v0.0.11",
                "constraint": "v0.0.11",
                "updateable": "v0.0.11",
                "latest": "v0.0.12",
            }
        ],
    )

    availability = mars.check_upgrade_availability()

    assert availability == mars.UpgradeAvailability(
        within_constraint=(),
        beyond_constraint=("meridian-base",),
    )


def test_check_upgrade_availability_classifies_range_update_as_within_constraint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_outdated_payload(
        monkeypatch,
        [
            {
                "source": "meridian-dev-workflow",
                "locked": "v0.4.1",
                "constraint": "^0.4",
                "updateable": "v0.4.2",
                "latest": "v0.5.0",
            }
        ],
    )

    availability = mars.check_upgrade_availability()

    assert availability == mars.UpgradeAvailability(
        within_constraint=("meridian-dev-workflow",),
        beyond_constraint=(),
    )


def test_check_upgrade_availability_filters_up_to_date_and_head_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_outdated_payload(
        monkeypatch,
        [
            {
                "source": "meridian-base",
                "locked": "v0.1.2",
                "constraint": "^0.1",
                "updateable": "v0.1.2",
                "latest": "v0.1.2",
            },
            {
                "source": "anthropic-skills",
                "locked": "aabbccddeeff",
                "constraint": "HEAD",
                "updateable": "112233445566",
                "latest": "112233445566",
            },
        ],
    )

    availability = mars.check_upgrade_availability()

    assert availability == mars.UpgradeAvailability()


def test_check_upgrade_availability_handles_mixed_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_outdated_payload(
        monkeypatch,
        [
            {
                "source": "foo",
                "locked": "v1.0.0",
                "constraint": "^1",
                "updateable": "v1.1.0",
                "latest": "v2.0.0",
            },
            {
                "source": "bar",
                "locked": "v0.0.11",
                "constraint": "v0.0.11",
                "updateable": "v0.0.11",
                "latest": "v0.0.12",
            },
            {
                "source": "baz",
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
                "source": "foo",
                "locked": "v1.0.0",
                "constraint": "^1",
                "updateable": "v1.1.0",
                "latest": "v2.0.0",
            },
        ],
    )

    availability = mars.check_upgrade_availability()

    assert availability == mars.UpgradeAvailability(
        within_constraint=("foo",),
        beyond_constraint=("bar",),
    )


def test_check_upgrade_availability_skips_rows_missing_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_outdated_payload(
        monkeypatch,
        [
            {
                "source": "meridian-base",
                "locked": "v0.1.0",
                "constraint": "^0.1",
                "updateable": "v0.1.1",
            },
            {
                "source": "meridian-dev-workflow",
                "locked": "v0.2.0",
                "constraint": "^0.2",
                "updateable": "v0.2.1",
                "latest": "v0.2.2",
            },
        ],
    )

    availability = mars.check_upgrade_availability()

    assert availability == mars.UpgradeAvailability(
        within_constraint=("meridian-dev-workflow",),
        beyond_constraint=(),
    )


def test_check_upgrade_availability_skips_rows_with_blank_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_outdated_payload(
        monkeypatch,
        [
            {
                "source": "blank-latest-empty",
                "locked": "v1.0.0",
                "constraint": "v1.0.0",
                "updateable": "v1.0.0",
                "latest": "",
            },
            {
                "source": "blank-latest-space",
                "locked": "v2.0.0",
                "constraint": "v2.0.0",
                "updateable": "v2.0.0",
                "latest": " ",
            },
        ],
    )

    availability = mars.check_upgrade_availability()

    assert availability == mars.UpgradeAvailability()


def test_check_upgrade_availability_skips_rows_with_blank_locked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_outdated_payload(
        monkeypatch,
        [
            {
                "source": "blank-locked-empty",
                "locked": "",
                "constraint": "^1",
                "updateable": "v1.1.0",
                "latest": "v1.2.0",
            },
            {
                "source": "blank-locked-space",
                "locked": " ",
                "constraint": "^1",
                "updateable": "v1.1.0",
                "latest": "v1.2.0",
            },
        ],
    )

    availability = mars.check_upgrade_availability()

    assert availability == mars.UpgradeAvailability()


def test_check_upgrade_availability_skips_rows_with_blank_updateable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_outdated_payload(
        monkeypatch,
        [
            {
                "source": "blank-updateable-empty",
                "locked": "v1.0.0",
                "constraint": "^1",
                "updateable": "",
                "latest": "v1.2.0",
            },
            {
                "source": "blank-updateable-space",
                "locked": "v1.0.0",
                "constraint": "^1",
                "updateable": " ",
                "latest": "v1.2.0",
            },
        ],
    )

    availability = mars.check_upgrade_availability()

    assert availability == mars.UpgradeAvailability()


def test_check_upgrade_availability_passes_root_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(mars, "resolve_mars_executable", lambda: "/usr/bin/mars")
    observed: list[list[str]] = []

    def _fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        observed.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="[]",
            stderr="",
        )

    monkeypatch.setattr(mars.subprocess, "run", _fake_run)

    availability = mars.check_upgrade_availability(tmp_path)

    assert availability == mars.UpgradeAvailability()
    assert observed and observed[0][-2:] == ["--root", tmp_path.as_posix()]


@pytest.mark.parametrize(
    "completed",
    [
        subprocess.CompletedProcess(
            args=["/usr/bin/mars", "outdated", "--json"],
            returncode=2,
            stdout="",
            stderr="boom",
        ),
        subprocess.CompletedProcess(
            args=["/usr/bin/mars", "outdated", "--json"],
            returncode=0,
            stdout="{not-json}",
            stderr="",
        ),
        subprocess.CompletedProcess(
            args=["/usr/bin/mars", "outdated", "--json"],
            returncode=0,
            stdout='{"not":"a-list"}',
            stderr="",
        ),
    ],
)
def test_check_upgrade_availability_returns_none_on_failures(
    monkeypatch: pytest.MonkeyPatch,
    completed: subprocess.CompletedProcess[str],
) -> None:
    monkeypatch.setattr(mars, "resolve_mars_executable", lambda: "/usr/bin/mars")
    monkeypatch.setattr(mars.subprocess, "run", lambda *_args, **_kwargs: completed)

    assert mars.check_upgrade_availability() is None


def test_check_upgrade_availability_returns_none_without_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mars, "resolve_mars_executable", lambda: None)

    assert mars.check_upgrade_availability() is None


def test_format_upgrade_availability_hint_only_within_constraint() -> None:
    lines = mars.format_upgrade_availability(
        mars.UpgradeAvailability(within_constraint=("meridian-base",))
    )

    assert lines == (
        "hint: 1 update available within your pinned constraint: meridian-base.",
        "      Run `meridian mars upgrade` to apply.",
    )


def test_format_upgrade_availability_hint_only_beyond_constraint() -> None:
    lines = mars.format_upgrade_availability(
        mars.UpgradeAvailability(beyond_constraint=("meridian-base",))
    )

    assert lines == (
        "hint: 1 newer version available beyond your pinned constraint: meridian-base.",
        "      Edit mars.toml to bump the version, then run `meridian mars sync`.",
    )


def test_format_upgrade_availability_hint_with_both_categories() -> None:
    lines = mars.format_upgrade_availability(
        mars.UpgradeAvailability(
            within_constraint=("foo", "bar"),
            beyond_constraint=("meridian-base",),
        )
    )

    assert lines == (
        "hint: 2 updates available within your pinned constraint: foo, bar.",
        "      Run `meridian mars upgrade` to apply.",
        "      1 newer version available beyond your pinned constraint: meridian-base.",
        "      Edit mars.toml to bump the version, then run `meridian mars sync`.",
    )


def test_format_upgrade_availability_warning_omits_hint_prefix() -> None:
    lines = mars.format_upgrade_availability(
        mars.UpgradeAvailability(
            within_constraint=("foo",),
            beyond_constraint=("meridian-base",),
        ),
        style="warning",
    )

    assert lines == (
        "1 update available within your pinned constraint: foo.",
        "      Run `meridian mars upgrade` to apply.",
        "      1 newer version available beyond your pinned constraint: meridian-base.",
        "      Edit mars.toml to bump the version, then run `meridian mars sync`.",
    )


def test_format_upgrade_availability_empty() -> None:
    assert mars.format_upgrade_availability(mars.UpgradeAvailability()) == ()

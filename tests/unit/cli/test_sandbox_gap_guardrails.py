from pathlib import Path

import meridian.cli.main as cli_main
import meridian.lib.ops as ops_pkg
import meridian.lib.ops.diag as diag


def test_startup_entrypoint_does_not_reference_removed_doctor_cache_helpers() -> None:
    source = Path(cli_main.__file__).read_text(encoding="utf-8")

    assert "consume_doctor_cache_warning" not in source
    assert "maybe_start_background_doctor_scan" not in source
    assert "_is_doctor_scan_launch_path" not in source


def test_startup_and_doctor_do_not_reference_legacy_doctor_cache_path() -> None:
    for module in (cli_main, diag):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "doctor-cache.json" not in source
        assert "doctor_cache_path" not in source


def test_obsolete_doctor_cache_module_and_dedicated_tests_stay_removed() -> None:
    ops_dir = Path(ops_pkg.__path__[0])

    assert not (ops_dir / "doctor_cache.py").exists()
    assert not (Path("tests/unit/ops") / "test_doctor_cache.py").exists()
    assert not any(Path("tests/integration").rglob("*doctor_cache*"))

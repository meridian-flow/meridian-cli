"""Configurable mock harness process used by integration tests."""

import argparse
import json
import os
import sys
import time
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mock meridian harness")
    parser.add_argument("--exit-code", type=int, default=0, help="Exit code to return")
    parser.add_argument("--duration", type=float, default=0.0, help="Delay in seconds before exit")
    parser.add_argument("--tokens", type=str, default="", help="JSON object for token usage")
    parser.add_argument("--stderr", type=str, default="", help="Message to print to stderr")
    parser.add_argument("--hang", action="store_true", help="Sleep forever until killed")
    parser.add_argument("--write-report", type=str, default="", help="Report text to write")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="Directory where report.md is written",
    )
    parser.add_argument(
        "--stdout-file",
        type=Path,
        default=None,
        help="Line-oriented file to stream",
    )
    parser.add_argument(
        "--crash-after-lines",
        type=int,
        default=None,
        help="Crash after emitting N lines from --stdout-file",
    )
    parser.add_argument(
        "--stream-delay",
        type=float,
        default=0.0,
        help="Delay in seconds between streamed stdout lines",
    )
    parser.add_argument(
        "--capture-json",
        type=Path,
        default=None,
        help="Optional file where argv + selected env vars are recorded as JSON",
    )
    return parser


def stream_stdout(file_path: Path, crash_after_lines: int | None, stream_delay: float) -> None:
    lines = file_path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines, start=1):
        print(line, flush=True)
        if stream_delay > 0:
            time.sleep(stream_delay)
        if crash_after_lines is not None and index >= crash_after_lines:
            raise RuntimeError("mock harness forced crash")


def maybe_write_report(message: str, report_dir: Path | None) -> None:
    if not message:
        return
    if report_dir is None:
        raise ValueError("--write-report requires --report-dir")
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.md").write_text(f"# Mock Report\n\n{message}\n", encoding="utf-8")


def maybe_capture_json(path: Path | None) -> None:
    if path is None:
        return

    payload = {
        "argv": sys.argv[1:],
        "env": {
            key: value
            for key, value in os.environ.items()
            if key.startswith("MERIDIAN_") or key == "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = build_parser()
    args, _unknown = parser.parse_known_args()

    if args.stderr:
        print(args.stderr, file=sys.stderr, flush=True)

    if args.tokens:
        parsed_tokens = json.loads(args.tokens)
        print(json.dumps({"tokens": parsed_tokens}, sort_keys=True), flush=True)

    if args.stdout_file is not None:
        try:
            stream_stdout(args.stdout_file, args.crash_after_lines, args.stream_delay)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr, flush=True)
            return 70

    maybe_capture_json(args.capture_json)
    maybe_write_report(args.write_report, args.report_dir)

    if args.duration > 0:
        time.sleep(args.duration)

    if args.hang:
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            return 130

    return args.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

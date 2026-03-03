# Backlog Execution Anomalies

## 2026-03-02

- Smoke setup mismatch: attempted `meridian space create`, but the command does not exist in current CLI (`space start`, `space list`, `space show`, `space close`, `space resume` are available).
- Workaround used: created smoke test spaces with `space_file.create_space(...)` via `uv run python`, then ran the real CLI behavior under test with `uv run meridian ...`.
- Smoke validation quirk: `rg` interprets patterns that begin with `--` as flags unless `--` is provided before the pattern.
- Workaround used: switched to `rg -o -- "--budget-per-spawn-usd"` when checking help output.

## 2026-03-03

- Test harness anomaly: calling `meridian.cli.main.main([...])` inside pytest cases can reconfigure structlog against capture-managed streams, then later tests may hit `ValueError: I/O operation on closed file` from structlog `PrintLogger`.
- Workaround used: tests that needed root-command validation switched from `main([...])` to direct `app([...])` assertions (expecting `ValueError` for error cases), which avoids global logging reconfiguration side effects.

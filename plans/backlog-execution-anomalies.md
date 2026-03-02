# Backlog Execution Anomalies

## 2026-03-02

- Smoke setup mismatch: attempted `meridian space create`, but the command does not exist in current CLI (`space start`, `space list`, `space show`, `space close`, `space resume` are available).
- Workaround used: created smoke test spaces with `space_file.create_space(...)` via `uv run python`, then ran the real CLI behavior under test with `uv run meridian ...`.

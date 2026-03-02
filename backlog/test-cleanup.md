# Test Cleanup Backlog

Date added: 2026-03-02

## 1) Consolidate CLI spawn plumbing tests
- Status: `todo`
- Priority: `medium`
- Goal: Merge overlapping CLI plumbing tests into a single parametrized suite.
- Current files:
  - `tests/test_cli_spawn_show_flags.py`
  - `tests/test_cli_spawn_stats.py`
  - `tests/test_cli_spawn_wait_multi.py`
  - `tests/test_cli_spawn_stream_flags.py`
- Proposed direction:
  - Create `tests/test_cli_spawn_plumbing.py` with parameterized payload/exit-code assertions.

## 2) Remove overlapping streaming test coverage
- Status: `todo`
- Priority: `medium`
- Goal: Keep one authoritative suite for subrun protocol/event enrichment behavior.
- Current overlap:
  - `tests/test_streaming_s5_subspawn_enrichment.py`
  - `tests/test_spawn_output_streaming.py`
- Proposed direction:
  - Fold unique assertions into the canonical file and remove duplicate cases.

## 3) Centralize subprocess test helpers
- Status: `todo`
- Priority: `medium`
- Goal: Reduce repeated helper boilerplate in CLI integration tests.
- Current duplication examples:
  - `_spawn_cli`, `_write_skill`, `_write_config` helpers across multiple test modules.
- Proposed direction:
  - Add shared test helper module (for example, `tests/helpers/cli.py` and `tests/helpers/fixtures.py`).

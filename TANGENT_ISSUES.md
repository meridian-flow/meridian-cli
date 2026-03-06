# Tangent Issues

Append-only log of issues found during spawn output overhaul implementation.
Not blocking the current step, but worth coming back to.

---

## Step 1: `extra_args` duplication is unsafe

**Found by**: gpt-5.4 propagation review (p14)

If someone passes `extra_args=("--json",)` to a codex spawn, the final command gets `--json` twice (once from `BASE_COMMAND`, once from `extra_args`). The installed `codex-cli 0.111.0` rejects duplicate `--json` with an error.

**Impact**: Any code or agent profile that manually adds `--json` to extra_args will break after Step 1.

**Fix options**:
1. Deduplicate in `build_harness_command()` before appending extra_args
2. Document that `--json` should never be in extra_args (fragile)

**Files**: `src/meridian/lib/harness/_strategies.py:113`

---

## Step 1: `extra_args` test coverage dropped

**Found by**: gpt-5.4 review (p12)

Removing `extra_args=("--json",)` from `_sample_run()` means no concrete adapter test now exercises arbitrary `extra_args` passthrough. The mechanism still works, but there's no regression test for it.

**Files**: `tests/test_flag_strategy.py`

---

## Step 2: Claude CLI requires `--verbose` with `--output-format stream-json` in `-p` mode

**Found by**: opus smoke test failure (p21, p25) — Claude CLI itself errors with:
`Error: When using --print, --output-format=stream-json requires --verbose`

**Impact**: Step 2's `BASE_COMMAND` change needs `--verbose` added too, or all Claude child spawns fail immediately.

**Resolution**: Added `--verbose` to `BASE_COMMAND`. This may have side effects on Claude's output verbosity — need to verify the stream event format doesn't change.

---

## Step 3: Duplicated assistant-message parsing

**Found by**: gpt-5.4 code smell review (p32)

Assistant-message parsing is duplicated and drifting between `src/meridian/lib/ops/_spawn_query.py:125` and `src/meridian/lib/extract/report.py:22`. The query path handles plain assistant/codex markers and category == "assistant"; the report path falls back to the last non-JSON line and joins text differently. Future fixes will drift unless this becomes one shared helper.

**Files**: `src/meridian/lib/ops/_spawn_query.py`, `src/meridian/lib/extract/report.py`

---

## Step 3: Output models mix transport, rendering, and compatibility

**Found by**: gpt-5.4 code smell review (p32)

The output models mix transport, CLI rendering, and compatibility shims in one place. `_spawn_models.py` embeds display logic directly in dataclasses and still carries compatibility-only fields. That makes the output surface harder to simplify and reason about.

**Files**: `src/meridian/lib/ops/_spawn_models.py`

---

## Step 3: _detail_from_row() is overloaded

**Found by**: gpt-5.4 code smell review (p32)

`_detail_from_row()` is no longer a mapper; it does file I/O, artifact extraction, running-log parsing, truncation, and final shaping. That coupling will keep attracting more special cases unless the data collection step is split from the pure output-construction step.

**Files**: `src/meridian/lib/ops/_spawn_query.py`

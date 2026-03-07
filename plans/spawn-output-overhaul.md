# Spawn Output Overhaul

**Status:** completed (Steps 1-11, 2026-03-06). Step 12/13 (CLI command refinements) deferred as follow-up.

## Philosophy

Agents are consumers, not debuggers. The spawn output answers one question: **"what happened?"** — status, report, done. Everything else is noise for the consumer and belongs in files for whoever needs to dig deeper.

- **One mode for spawn**: `meridian spawn` always outputs the same minimal JSON result, side effects to files. No implicit mode switching based on `MERIDIAN_SPACE_ID`. Humans and agents need the same thing: did it work, and what did it produce. Note: the global CLI transport layer (`AgentSink` envelope wrapping for nested agents) is a separate concern — this plan scopes to the spawn output content, not the transport protocol.
- **Result over metadata**: The consumer wants the report, not which model ran or what flags were passed. It already knows — it made the call.
- **Files for depth**: Input params, raw harness output, stderr logs, token usage — all in the spawn directory. Not forced into every response.
- **Clean signal**: Null fields are noise. Input echo is noise. Filler messages are noise. Strip it all.
- **Don't gate on ceremony**: A spawn succeeds when the harness exits 0. Not when the agent writes a report in the right format. The report is output, not a success criterion.
- **Explicit opt-in for extras**: If a human wants to watch live progress, they pass `--stream`. That's an explicit choice, not an implicit mode.

## Why

The spawn CLI output is broken in multiple compounding ways:

1. **Codex runs without `--json`**, so stdout is empty. No JSON events captured to `output.jsonl`. This means streaming shows nothing, report fallback extraction finds nothing, and every codex spawn gets `missing_report` → hard failure, even when the agent worked fine.

2. **`missing_report` is a hard failure**. Any agent that doesn't explicitly call `meridian report create --stdin` fails. The fallback extraction exists but can't help when `output.jsonl` is empty (because of #1).

3. **The output is 18 fields of noise**. Most null, most echoing back input the caller already knows. `"composed_prompt": null, "current_depth": null, "background": false`.

4. **Report content isn't in the output**. Only `report_path` (pointing to the wrong place). Consuming agents have to find and read a file to get the result.

5. **Two divergent output modes**. Text mode for humans, JSON for agents, with different code paths (`_emit_spawn_text`, `_emit_spawn_dry_run_text`, format routing in `emit()`). The text mode reads reports from disk, truncates them, formats metadata lines — all separate from the JSON path. This is unnecessary complexity because both consumers want the same thing.

6. **Overengineered streaming**. `TerminalEventFilter` with configurable category presets (`OutputConfig.show`, `verbosity`), three visibility tiers, `_HUMAN_ONLY` flag hiding. All to solve "should the human see progress?" — which should just be a `--stream` flag that tees stderr through.

7. **Stderr leaks into agent mode**. `harness stderr: ...` prints before JSON output, corrupting it.

8. **No `params.json` per spawn**. Debugging means parsing a shared `spawns.jsonl` instead of looking at a self-contained spawn directory.

These aren't independent bugs — they're a chain. Fix `--json` and extraction works. Unify output and half the CLI code disappears. Put results in files and the spawn dir becomes self-contained.

## What

### 1. Pass `--json` to codex

Add `--json` to codex adapter's command building. This is the single change that unblocks everything else — with structured JSON events on stdout, the capture/extraction/streaming pipeline works.

Orchestrate (our working shell-script predecessor) has always passed `--json`:
```bash
CLI_CMD_ARGV=(codex exec -m "$MODEL" ... --json -)
```

**Concrete changes**:
- `codex.py:51` — change `BASE_COMMAND` from `("codex", "exec")` to `("codex", "exec", "--json")`. This is the non-interactive (child spawn) command. The `PRIMARY_BASE_COMMAND` (`("codex",)`) stays unchanged — primary/interactive codex launches don't need `--json`.
- Alternative: keep `BASE_COMMAND` unchanged, add a `"json_output"` strategy with `FlagEffect.CLI_FLAG` and `cli_flag="--json"`. But `--json` is not a SpawnParams field — it's always-on for codex exec. Simpler to put it in `BASE_COMMAND`.

**Test gap**: Current tests in `test_flag_strategy.py` inject `--json` via `extra_args`, so they pass regardless. After changing `BASE_COMMAND`, those tests will have a duplicate `--json` — update their expected output to not double-count it. Also add a test that verifies `build_command()` output includes `--json` without any `extra_args`.

**Doc update**: `docs/harness-adapters.md:41` still shows `codex exec` without `--json` — update to match.

**Files**: `src/meridian/lib/harness/codex.py`, `tests/test_flag_strategy.py`, `docs/harness-adapters.md`

### 2. Add `--output-format stream-json` to claude

Claude adapter uses `BASE_COMMAND = ("claude", "-p")` at `claude.py:177`. The `-p` flag (pipe mode) defaults to `text` output, not `stream-json` — verified via `claude -p --help`. Without explicit `--output-format stream-json`, the claude adapter has the same class of bug as codex: stdout is unstructured text, not JSON events.

**Concrete changes**:
- `claude.py:177` — change `BASE_COMMAND` from `("claude", "-p")` to `("claude", "-p", "--output-format", "stream-json")`. Same rationale as step 1: this is always-on for child spawns, not a per-spawn toggle.
- Alternatively, add via strategy if `--output-format` needs to vary. But for child spawns it's always `stream-json`.

**Files**: `src/meridian/lib/harness/claude.py`

### 3. Downgrade `missing_report` from hard failure

If the harness exits 0, the spawn succeeded. A missing report means the agent didn't say much — that's `report: null`, not `status: failed`. The report is output, not a success criterion.

**Concrete changes** at `exec/spawn.py:634-639`:
```python
# BEFORE:
if exit_code == 0 and _spawn_kind(space_dir, run.spawn_id) == "child":
    if extracted.report.content is None:
        exit_code = 1
        failure_reason = "missing_report"
        break

# AFTER:
if exit_code == 0 and _spawn_kind(space_dir, run.spawn_id) == "child":
    if extracted.report.content is None:
        failure_reason = "missing_report"  # keep signal, don't override exit code
        # Don't break — proceed to remaining checks (guardrails, etc.)
```

Remove the `exit_code = 1` override and the `break`. The `missing_report` string stays in the spawn record for diagnostic queries but no longer forces failure. The `empty_output` path at L641 stays — truly empty output (no stdout at all) is a different failure mode.

**Display-layer fix**: The query/display path surfaces `failure_reason` as a "Failure" label in `_spawn_models.py:245` (via `_spawn_query.py:285`). After this change, a succeeded spawn can have `failure_reason = "missing_report"` — which would confusingly render as "Failure" even though `status = "succeeded"`. Fix: the display logic should only show the failure label when `status` is actually `"failed"`. If `status` is `"succeeded"` and `failure_reason` is set, render it as a warning instead (e.g., "Warning: missing_report").

**Files**: `src/meridian/lib/exec/spawn.py`, `src/meridian/lib/ops/_spawn_models.py`, `src/meridian/lib/ops/_spawn_query.py`

### 4. Write `params.json` per spawn

At spawn init, write resolved execution params to `.meridian/.spaces/<space>/spawns/<id>/params.json`. Source from the `_PreparedCreateLike` protocol fields.

**Concrete changes** in `_spawn_execute.py`, add after `_init_spawn()` returns (around L583 in `_execute_spawn_blocking` and L583 in `_execute_spawn_background`):
```python
params_path = resolve_spawn_log_dir(runtime.repo_root, spawn.spawn_id, context.space_id) / "params.json"
params_path.parent.mkdir(parents=True, exist_ok=True)
params_payload = {
    "model": prepared.model,
    "harness": prepared.harness_id,
    "agent": prepared.agent_name,
    "prompt_length": len(prepared.composed_prompt),
    "reference_files": list(prepared.reference_files),
    "template_vars": prepared.template_vars,
    "skills": list(prepared.skills),
    "permission_tier": prepared.permission_config.tier.value,
    "continue_session": prepared.continue_harness_session_id,
    "continue_fork": prepared.continue_fork,
}
import json, tempfile
# Atomic write: tmp+rename consistent with .meridian/.spaces/ state convention
fd, tmp = tempfile.mkstemp(dir=str(params_path.parent), suffix=".tmp")
try:
    with os.fdopen(fd, "w") as f:
        json.dump(params_payload, f, indent=2)
    os.replace(tmp, params_path)  # os.replace for cross-device safety, matches repo practice
except BaseException:
    Path(tmp).unlink(missing_ok=True)
    raise
```
This follows the repo's file-state convention (atomic writes via tmp+rename) for all state under `.meridian/.spaces/<space-id>/`. Uses `os.replace()` (not `Path.rename()`) to match existing helpers like `space_file.py:45` and `config.py:551`. No `fcntl.flock` needed here since `params.json` is written once at spawn init before execution begins — no concurrent writers.

Don't include composed_prompt content (can be large). Include `prompt_length` for diagnostics.

Spawn directory becomes self-contained:
```
.meridian/.spaces/<space>/spawns/<id>/
  params.json      — resolved execution parameters
  report.md        — what was produced
  output.jsonl     — raw harness output (JSON events)
  stderr.log       — harness diagnostics
  tokens.json      — token usage
```

**Files**: `src/meridian/lib/ops/_spawn_execute.py`

### 5. Add `report` field to `SpawnActionOutput`, populate from finalization

After spawn completes, read report content into `SpawnActionOutput.report`. The extraction pipeline already exists — just wire it into the output.

**Concrete changes**:

1. `_spawn_models.py:41` — add `report: str | None = None` to `SpawnActionOutput` dataclass fields (after `report_path`).

2. `_spawn_execute.py` in `_execute_spawn_blocking()` at L748 — after `_read_spawn_row()`, add:
```python
from ._spawn_query import _read_report_text
_, report_text = _read_report_text(runtime.repo_root, str(spawn.spawn_id), space=space_id_str)
```
Then include `report=report_text` in the `SpawnActionOutput(...)` constructor at L787.

3. The executor (`execute_with_finalization`) returns just an `int` exit code — no need to change its return shape. Report reading happens post-finalization in the ops layer where we already read the spawn row.

**Files**: `src/meridian/lib/ops/_spawn_models.py`, `src/meridian/lib/ops/_spawn_execute.py`

### 6. Unify output: always JSON, always minimal

This is the big simplification. ALL `SpawnActionOutput` emissions go through JSON, regardless of output format setting. This applies to spawn create, cancel, and continue (all commands that return `SpawnActionOutput`).

**External output** (what the caller sees on stdout):
```json
{
  "spawn_id": "p2",
  "status": "succeeded",
  "duration_secs": 13.74,
  "report": "## What Was Done\n..."
}
```

Null fields omitted. No input echo. No metadata. Six fields max.

For dry-run, include `composed_prompt` and `cli_command` (the point of dry-run).
For background, include just `spawn_id` and `status: "running"`.

**Concrete changes**:

1. `_spawn_models.py` — add `to_wire()` method to `SpawnActionOutput`:
```python
def to_wire(self) -> dict[str, object]:
    """Project minimal external JSON shape. Omit nulls and input echo."""
    wire: dict[str, object] = {"spawn_id": self.spawn_id, "status": self.status}
    if self.duration_secs is not None:
        wire["duration_secs"] = round(self.duration_secs, 2)
    if self.report is not None:
        wire["report"] = self.report
    if self.error is not None:
        wire["error"] = self.error
    if self.warning is not None:
        wire["warning"] = self.warning
    if self.exit_code is not None:
        wire["exit_code"] = self.exit_code
    # Dry-run extras
    if self.status == "dry-run":
        if self.composed_prompt is not None:
            wire["composed_prompt"] = self.composed_prompt
        if self.cli_command:
            wire["cli_command"] = list(self.cli_command)
    return wire
```

2. `cli/main.py:220-240` — change `emit()` to intercept ALL `SpawnActionOutput` (not just `spawn.create`), project via `to_wire()`, but **still route through the resolved sink**. This preserves AgentSink behavior for nested agents — AgentSink wraps output in typed message envelopes, and bypassing it would break the nested-agent transport protocol:
```python
def emit(payload: object) -> None:
    options = get_global_options()
    sink, flush_after = _resolve_sink(options)
    if isinstance(payload, SpawnActionOutput):
        # Project to minimal wire shape, then emit through the sink.
        # Do NOT print directly to stdout — that would bypass AgentSink
        # envelope wrapping for nested-agent runs.
        wire = payload.to_wire()
        emit_output(wire, sink=sink)
        if flush_after:
            flush_sink(sink)
        return
    emit_output(payload, sink=sink)
    if flush_after:
        flush_sink(sink)
```
Note: `emit_output(wire, sink=sink)` sends a plain dict, not a dataclass. All three sinks handle it:
- `JsonSink` (`output.py:139`): `json.dumps()` → single-line JSON ✅
- `AgentSink` (`output.py:171`): wraps in typed envelope → correct ✅
- `TextSink` (`output.py:81`): falls through to JSON since dict has no `format_text()`, but **will pretty-print with indentation** (multiline), not single-line. This means TextSink output shape differs slightly from JsonSink. If strict "one shape" matters, add a `TextSink` branch that emits single-line JSON for dicts. Otherwise accept that TextSink (human-facing) gets readable multiline and JsonSink (machine-facing) gets compact — which is a reasonable divergence.

3. **Delete from `cli/main.py`**:
   - `_spawn_spawn_metadata_line()` (L118-130) — no text mode metadata
   - `_find_spawn_report_file()` (L133-154) — report is in the JSON
   - `_read_spawn_report_text()` (L157-162) — report is in the JSON
   - `_truncate_spawn_error_text()` (L165-170) — no truncation
   - `_truncate_spawn_failure_fields()` (L173-180) — no truncation
   - `_emit_spawn_text()` (L183-209) — no text mode
   - `_emit_spawn_dry_run_text()` (L212-217) — handled by to_wire()
   - `_SPAWN_ERROR_TEXT_LIMIT` and `_SPAWN_ERROR_TRUNCATED_SUFFIX` constants (L51-52)
   - `from meridian.lib.ops.spawn import SpawnActionOutput` import (L32) — keep if still needed for isinstance check

4. **MCP path** (`server/main.py:35`): MCP uses `to_jsonable(result)` which serializes ALL fields. Change MCP handler to use `to_wire()` for SpawnActionOutput:
```python
async def _tool(**kwargs):
    payload = coerce_input_payload(op.input_type, kwargs)
    result = await op.handler(payload)
    if hasattr(result, 'to_wire'):
        return result.to_wire()
    return to_jsonable(result)
```
Or add to_wire awareness to the generic path. This keeps MCP output clean too.

**Files**: `src/meridian/lib/ops/_spawn_models.py`, `src/meridian/cli/main.py`, `src/meridian/server/main.py`

### 7. Remove `--report-path` CLI flag

Dead weight. The `build_report_instruction()` at `compose.py:21-35` accepts `report_path` but only validates it's non-empty — the actual instruction text doesn't use the path value. It always says `meridian report create --stdin`.

**Concrete changes**:
- `cli/spawn.py:80-87` — remove `report_path` parameter from `_spawn_create()`
- `_spawn_models.py:25` — remove `report_path` field from `SpawnCreateInput` (or default to hardcoded `"report.md"` and stop threading it)
- `_spawn_prepare.py:58` — remove `report_path` from `_PreparedCreate`
- `_spawn_prepare.py:279` — remove `report_path=payload.report_path` from `compose_run_prompt_text()` call
- `_spawn_prepare.py:397` — remove `report_path=Path(...)` from `_PreparedCreate(...)` constructor
- `_spawn_execute.py:79` — remove `report_path` from `_PreparedCreateLike` protocol
- `_spawn_execute.py` — remove all `report_path=prepared.report_path` from `SpawnActionOutput(...)` constructors (multiple sites)
- `_spawn_models.py:55` — remove `report_path` from `SpawnActionOutput`
- `compose.py:21-35` — remove `report_path` parameter from `build_report_instruction()`, inline the validation
- `compose.py:83,135,155,168` — remove `report_path` parameter threading through compose functions

**Test updates**:
- `tests/test_prompt_slice3.py:117` — remove `report_path` kwarg from compose call
- `tests/test_prompt_slice3.py:136` — remove `report_path` kwarg from compose call
- Grep for any other test files passing `report_path`

**Files**: `src/meridian/cli/spawn.py`, `src/meridian/lib/ops/_spawn_models.py`, `src/meridian/lib/ops/_spawn_prepare.py`, `src/meridian/lib/ops/_spawn_execute.py`, `src/meridian/lib/prompt/compose.py`, `tests/test_prompt_slice3.py`

### 8. Simplify streaming for spawn

Remove `TerminalEventFilter` usage from the **spawn execution path** only. Don't touch `OutputConfig` or the filter itself — `spawn wait` and other commands may still use them. This step is scoped to spawn, not repo-wide config cleanup.

Replace with two modes for spawn execution:
- **Default** (no flags): stdout captured to `output.jsonl`, stderr captured to `stderr.log`. No terminal output during execution. Caller gets the JSON result when done.
- **`--stream`**: tee both stdout and stderr to terminal while also capturing to files. Raw passthrough, no parsing or filtering.

**Concrete changes** in `_spawn_execute.py:686-701`:
```python
# BEFORE:
stream_stdout_to_terminal = payload.stream
if not payload.stream:
    event_filter = TerminalEventFilter(...)
    event_observer = event_filter.observe

# AFTER:
stream_stdout_to_terminal = payload.stream
event_observer = None  # no filtering in spawn path
```

Also at L743 — remove `verbose`-driven stderr tee:
```python
# BEFORE:
stream_stderr_to_terminal=payload.stream or payload.verbose,
# AFTER:
stream_stderr_to_terminal=payload.stream,
```

Remove unused imports from `_spawn_execute.py`:
- `TerminalEventFilter` (L27)
- `resolve_visible_categories` (L29)
- These imports come from `meridian.lib.exec.terminal`

The `--verbose` and `--quiet` flags stay on the CLI for now (they affect other code paths) but become no-ops for spawn execution.

**Files**: `src/meridian/lib/ops/_spawn_execute.py`

### 9. Suppress stderr emission on failure

`_spawn_execute.py:753-763` reads `stderr.log` and emits a summary via `sink.status()` on failure. This corrupts JSON output. The stderr is already in the file — if the caller wants it, they read the file.

**Concrete changes**: Delete the block at `_spawn_execute.py:753-763`:
```python
# DELETE this entire block:
if status == "failed" and not payload.stream and not payload.verbose:
    stderr_path = resolve_spawn_log_dir(...) / "stderr.log"
    if stderr_path.is_file():
        stderr_text = stderr_path.read_text(...)
        rendered_stderr = format_stderr_for_terminal(...)
        if rendered_stderr is not None:
            runtime.sink.status(rendered_stderr)
```

Also remove unused import: `format_stderr_for_terminal` from `meridian.lib.exec.terminal` (L28).

**Note**: Steps 8 and 9 should be implemented together — they're tightly coupled. Step 8 removes the streaming filter, step 9 removes the failure stderr dump. Together they make the spawn path silent (no terminal output) unless `--stream` is passed.

**Files**: `src/meridian/lib/ops/_spawn_execute.py`

### 10. Remove porcelain output format

The entire `--porcelain` code path is dead weight — tab-separated key=value output that nothing uses.

**Concrete changes**:

In `output.py`:
- L14: Change `OutputFormat = Literal["text", "json", "porcelain"]` → `OutputFormat = Literal["text", "json"]`
- L34-53: Remove `porcelain_mode` parameter from `normalize_output_format()`, remove the `if porcelain_mode: return "porcelain"` branch, remove `"porcelain"` from the valid set in normalization
- L56-78: Delete `_porcelain_value()`, `_porcelain_line()`, `_porcelain_lines()`
- L101-105: Remove porcelain branch from `TextSink.result()`
- L216-217: Remove `"porcelain"` from `create_sink()` format routing

In `main.py`:
- L243-273: Remove `--porcelain`/`--no-porcelain` handling from `_extract_global_options()`
- L318-322: Remove `porcelain_mode=porcelain_mode` from `normalize_output_format()` call
- L368-389: Remove `porcelain` parameter from `root()` function
- L454-457: Remove `porcelain_mode=porcelain` from second `normalize_output_format()` call
- L876-884: Remove `"--porcelain"`, `"--no-porcelain"` from `_TOP_LEVEL_BOOL_FLAGS`
- L961: Remove `porcelain_mode=...` from `normalize_output_format()` call in `main()` logging check (if present — verify)

**Test/doc cleanup**:
- `tests/SMOKE_TESTING.md:728` — remove porcelain assertions
- `tests/ACTUALLY_IMPORTANT/harness-layer-cleanup.md:17` — remove porcelain references
- Grep for any other `porcelain` references in tests/docs

**Files**: `src/meridian/cli/output.py`, `src/meridian/cli/main.py`, `tests/SMOKE_TESTING.md`, `tests/ACTUALLY_IMPORTANT/harness-layer-cleanup.md`

### 11. Remove `SpawnActionOutput.format_text()`

After step 6, ALL `SpawnActionOutput` emissions go through JSON (create, cancel, continue). The `format_text()` method at `_spawn_models.py:62-91` becomes dead code.

**Prerequisite**: Step 6 must route cancel and continue through JSON output, not just create. Verify that `main.py:emit()` intercepts all `isinstance(payload, SpawnActionOutput)` — the condition at L226-227 currently checks `payload.command == "spawn.create"`. Step 6 removes this check so all SpawnActionOutput goes through `to_wire()`.

**Concrete changes**:
- `_spawn_models.py:62-91` — delete `format_text()` method from `SpawnActionOutput`
- Keep the `FormatContext` import at L11-12 — other output types (`SpawnDetailOutput` at L123, etc.) still use it

**Keep**:
- `SpawnStatsOutput.format_text()` — used by `spawn stats`
- `SpawnDetailOutput.format_text()` — used by `spawn show`
- `SpawnWaitMultiOutput.format_text()` — used by `spawn wait`
- `SpawnListOutput.format_text()` — used by `spawn list`
- `TextFormattable` protocol and `_render_text()` in `TextSink` — still needed by these commands

**Files**: `src/meridian/lib/ops/_spawn_models.py`

### 12. Deduplicate `_minutes_to_seconds()`

Identical function exists in both `_spawn_execute.py:64` and `spawn.py:65`. Move to a shared utility.

**Concrete changes**:
- Create or use `src/meridian/lib/ops/_utils.py` (already exists — has `merge_warnings`)
- Move `_minutes_to_seconds()` there
- Update imports in both files

**Files**: `src/meridian/lib/ops/_spawn_execute.py`, `src/meridian/lib/ops/spawn.py`, `src/meridian/lib/ops/_utils.py`

### 13. Refine existing CLI commands — FOLLOW-UP

> **Not implementation-ready.** This step needs its own design pass before execution. Marking as follow-up to avoid blocking the core overhaul (steps 1-12).

**Why it's not ready:**
- `spawn show` defaulting to report-only is a bigger output contract change than listed — `SpawnDetailOutput` at `_spawn_models.py:215` has a full `format_text()` with metadata fields, and callers may depend on the current shape.
- `spawn files` with NUL-delimited output needs a raw stdout bypass — `TextSink.result()` at `output.py:101` always appends a newline, so piping through the normal sink breaks `xargs -0` semantics. Needs a CLI-only raw output path or a new sink mode.
- Handler registration at `cli/spawn.py:346` is only part of the work — also need op registration, input/output types, and MCP exposure decisions.

**Desired end state** (to be designed separately):

**`spawn show <id>`** — default to printing the report content (currently requires `--report`). `--metadata` flag shows the full spawn record.

**`spawn logs <id>`** — new command. Last assistant message from `output.jsonl`. `--stderr` for stderr log.

**`spawn files <id>`** — new command. NUL-delimited files touched. Pipeable to `xargs -0 git add`.

**Files**: TBD after design pass

### ~~14. Remove AgentSink~~ — OUT OF SCOPE

AgentSink is the transport layer for nested-agent mode, not spawn-specific. It wraps all JSON commands (not just spawn) with typed message envelopes when `MERIDIAN_SPACE_ID` is set. Removing it here would change the nested-agent transport protocol repo-wide, which contradicts the plan's own scope declaration: "the global CLI transport layer (AgentSink envelope wrapping for nested agents) is a separate concern."

Leave AgentSink, `_agent_sink_enabled()`, and `agent_mode` in `create_sink()` untouched. If AgentSink becomes redundant after the full output unification is complete, that's a separate follow-up.

## Order

```
Step 1:  Pass --json to codex            (unblocks extraction pipeline)
Step 2:  Verify claude stream-json       (same concern, quick check)
Step 3:  Downgrade missing_report        (warning, not failure)
Step 4:  Write params.json per spawn     (additive, self-contained spawn dirs)
Step 5:  Add report field, populate      (report content in output JSON)
Step 6:  Unify output: always minimal JSON (the big simplification — ALL SpawnActionOutput)
Step 7:  Remove --report-path            (dead flag + dead param threading)
Step 8:  Simplify spawn streaming +      (remove filter + suppress stderr together)
         suppress stderr on failure
Step 9:  Remove porcelain format         (dead code path)
Step 10: Remove SpawnActionOutput.format_text() (dead after step 6)
Step 11: Deduplicate _minutes_to_seconds (trivial cleanup)
Step 12: Refine CLI commands             (FOLLOW-UP — needs separate design pass)
```

### Dependency graph

```
Steps 1-4: independent, can run in parallel
Step 5: depends on 3 (report semantics change)
Step 6: depends on 5 (wire model includes report)
Step 7: depends on 6 (report_path references removed from output)
Step 8: independent of 6 (spawn execution path, not output)
Steps 9-10: depend on 6 (output path simplified)
Step 11: independent (trivial)
Step 12: independent (additive)
```

### Parallel execution opportunities

**Batch 1** (independent): Steps 1, 2, 3, 4
**Batch 2** (after 3): Step 5
**Batch 3** (after 5): Step 6
**Batch 4** (after 6, independent of each other): Steps 7, 8, 9, 10
**Any time**: Steps 11, 12

### Combined steps

Steps 8 (streaming) and 9 (stderr suppression) from the original plan are merged into one step because they're tightly coupled — both modify the same code block in `_execute_spawn_blocking` and together define the "silent by default" behavior.

## Verification

Each step:
```bash
uv run pytest-llm
uv run pyright
```

After step 1 (--json for codex):
```bash
MERIDIAN_SPACE_ID=test uv run meridian spawn -m gpt-5.3-codex -p "say hello"
cat .meridian/.spaces/test/spawns/p1/output.jsonl
# Should see JSON events (not raw text)
```

After step 6 (unified JSON output):
```bash
uv run meridian spawn -p "say hello"
# Minimal JSON: {"spawn_id":"p1","status":"succeeded","duration_secs":12.3,"report":"..."}
# No nulls, no input echo, no metadata noise

# Same output regardless of MERIDIAN_SPACE_ID:
MERIDIAN_SPACE_ID=test uv run meridian spawn -p "say hello"
# Identical shape

# --stream tees both stdout and stderr to terminal during execution
uv run meridian spawn --stream -p "say hello"
# See raw harness output in real-time, then JSON result

# Cancel also emits JSON:
uv run meridian spawn cancel p1
# {"spawn_id":"p1","status":"cancelled"}
```

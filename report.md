# Run/Space Plumbing Investigation Report

## Scope
Investigated run/space plumbing bugs around `run.spawn --space`, auto-created spaces, and report extraction/staleness. Traced code paths end-to-end and validated behavior with targeted local probes.

## Verification Performed
- Static trace across:
  - `src/meridian/lib/ops/run.py`
  - `src/meridian/lib/ops/_run_execute.py`
  - `src/meridian/lib/ops/_run_query.py`
  - `src/meridian/lib/ops/_run_prepare.py`
  - `src/meridian/lib/prompt/compose.py`
  - `src/meridian/lib/prompt/reference.py`
  - `src/meridian/lib/exec/spawn.py`
  - `src/meridian/cli/main.py`
  - `src/meridian/lib/state/artifact_store.py`, `id_gen.py`
- Dynamic probes (small Python scripts) confirming:
  - `run_create_sync(..., space='s1')` fails with `ERROR [SPACE_REQUIRED]` when `MERIDIAN_SPACE_ID` is unset.
  - `run_create_sync(...)` with auto-created space also fails the same way.
  - `run_list_sync(..., space='s1')` and `run_stats_sync(..., space='s1')` also fail without env space context.
  - Dry-run prompt generation does not include the `report_path` value; output `report_path` resolves against CWD.

## Bug 1 Root Cause: `run spawn --space` still fails with `SPACE_REQUIRED`

### What is happening
`payload.space` is threaded correctly into spawn execution, but a **post-run status read** falls back to env-only space resolution and throws.

### Code path
1. CLI passes `space` into `RunCreateInput`:
   - `src/meridian/cli/run.py:156-170`
2. `run_create_sync` keeps/threads payload:
   - `src/meridian/lib/ops/run.py:79-121`
3. Blocking execution resolves space from payload and runs fine:
   - `_resolve_space(...)` uses payload first: `src/meridian/lib/ops/_run_execute.py:272-276`
   - Execution itself uses that resolved space: `src/meridian/lib/ops/_run_execute.py:611-724`
4. After completion, blocking path calls `_read_run_row(...)`:
   - `src/meridian/lib/ops/_run_execute.py:736`
5. `_read_run_row` resolves space via `_require_space_id()` which is env-only:
   - `src/meridian/lib/ops/_run_query.py:68-69`
   - `src/meridian/lib/ops/_run_query.py:21-29`
6. With no `MERIDIAN_SPACE_ID`, it raises `SPACE_REQUIRED_ERROR`.

### Assessment
- Severity: **Critical (P0)**
- Fix scope: **Localized** (use already-resolved `space_dir` for post-run row read in blocking path; avoid env-dependent `_run_query` here).

## Bug 2 Root Cause: auto-created space not usable in same run

### What is happening
Auto-space creation works and payload is updated, but Bug 1’s post-run env-only read still fails.

### Code path
1. Auto-create space and patch payload:
   - `src/meridian/lib/ops/run.py:65-77`
2. Patched payload is used for execution:
   - `src/meridian/lib/ops/run.py:98-121`
3. Same failure point as Bug 1 after execution:
   - `src/meridian/lib/ops/_run_execute.py:736`
   - `src/meridian/lib/ops/_run_query.py:21-29,68-69`

### Assessment
- Severity: **Critical (P0)**
- Fix scope: **Localized** (same fix as Bug 1).

## Bug 3 Root Cause: `report.md` appears stale/not overwritten

This has two distinct plumbing issues that can surface as “stale report”:

### 3A) `report_path` is not a real write target in execution pipeline
- `report_path` is passed into prompt composition but not enforced as run output destination.
- `build_report_instruction(...)` no longer includes a file-path write instruction:
  - `src/meridian/lib/prompt/compose.py:20-32`
- `RunParams` has no `report_path` field:
  - `src/meridian/lib/harness/adapter.py:34-49`
- Finalization persists report to run log dir (`.../runs/<run-id>/report.md`) regardless:
  - `src/meridian/lib/extract/finalize.py:49-76,91-124`

So a workspace `report.md` file can remain old between runs if the harness/agent did not rewrite it explicitly.

### 3B) Report lookup and artifact addressing are run-id-only in places
- Run IDs are per-space (`r1`, `r2`, ...), so IDs repeat across spaces:
  - `src/meridian/lib/state/id_gen.py:55-59`
- CLI fallback lookup scans spaces and returns first matching `<space>/runs/<run_id>/report.md` when env space unset:
  - `src/meridian/cli/main.py:103-124`
- This can surface a report from a different space with the same run ID (looks like stale content).

### Additional report-path inconsistency
- `RunActionOutput.report_path` is resolved using `Path(payload.report_path).resolve()` (CWD-based), not repo-root-relative:
  - `src/meridian/lib/ops/_run_prepare.py:402`
- This can point to an unrelated path and add confusion.

### Assessment
- Severity: **High (P1)**
- Fix scope:
  - 3A: **Broader refactor** (decide authoritative report contract: per-run artifact only vs explicit user path write-through).
  - 3B: **Mixed**:
    - CLI lookup ambiguity is **localized**.
    - Run-id-only artifact namespace is **broader refactor**.

## Similar Plumbing Issues Found

1. `run list --space <id>` and `run stats --space <id>` still require env space.
- They call `_require_space_dir()` before honoring payload `space`/`no_space`.
- Files:
  - `src/meridian/lib/ops/run.py:53-55,128-136,166-171`
- Severity: **High (P1)**
- Scope: **Localized** (resolve selected space from payload first).

2. `run.show`, `run.wait`, and `run.continue` are env-coupled through `_read_run_row`.
- Calls:
  - `src/meridian/lib/ops/run.py:228-239,311-327,343-348`
- `_read_run_row` path:
  - `src/meridian/lib/ops/_run_query.py:68-69`
- Severity: **High (P1)** for explicit `--space` workflows / automation.
- Scope: **Broader** if cross-space lookup by run reference is desired; **localized** if requiring explicit `space` parameter additions.

3. `_detail_from_row` injects `space_id` from env, not from lookup context.
- File:
  - `src/meridian/lib/ops/_run_query.py:103-109`
- Severity: **Medium (P2)** (incorrect metadata possible).
- Scope: **Localized**.

4. `-f @name` reference loading ignores payload `space` and auto-created space.
- Uses `os.getenv("MERIDIAN_SPACE_ID")` directly.
- File:
  - `src/meridian/lib/prompt/reference.py:111-118`
- Severity: **High (P1)**
- Scope: **Broader** (thread explicit space context into prompt/reference loading APIs).

5. Artifact key namespace is `"{run_id}/..."` (no space component), but run IDs are per-space.
- Artifact key builder:
  - `src/meridian/lib/state/artifact_store.py:27-30`
- Run ID generation:
  - `src/meridian/lib/state/id_gen.py:55-59`
- Affected downstream readers include files-touched extraction via run-id-only artifact lookup:
  - `src/meridian/lib/ops/_run_query.py:80-87`
- Severity: **High (P1)** for multi-space correctness.
- Scope: **Broader refactor** (space-aware artifact keys and migration strategy).

## MCP Server Space Context Check

### Question
Does codex-launched MCP server inherit `MERIDIAN_SPACE_ID` when parent run used auto-created/explicit space?

### Findings
- Run execution sets child env overrides with resolved space:
  - `_run_child_env(..., space_id, ...)` sets `MERIDIAN_SPACE_ID`: `src/meridian/lib/ops/_run_execute.py:126-149`
- Execution merges these overrides into sanitized child env:
  - `src/meridian/lib/exec/spawn.py:112-132,501-507`
- Codex MCP sidecar is launched by codex process (`uv run --directory <repo_root> meridian serve`):
  - `src/meridian/lib/harness/codex.py:86-115`

### Conclusion
MCP sidecar inheritance is **not** the primary root cause for Bugs 1/2. The space loss occurs in post-run query helpers that read env directly, not in harness child env propagation.

## Recommended Fix Ordering
1. Fix blocking `run.spawn` post-run row read to avoid env-only lookup (Bugs 1/2).
2. Make `run.list`/`run.stats` honor explicit `space` without requiring env.
3. Make run query/detail helpers accept explicit space context (or persist `space_id` in run records).
4. Resolve report contract (`report_path` semantics vs per-run artifact), then align CLI output fields and prompt instruction.
5. Refactor artifact namespace to include space identity to eliminate cross-space key collisions.

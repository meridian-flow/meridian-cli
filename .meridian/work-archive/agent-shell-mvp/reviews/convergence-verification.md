`meridian spawn report create --stdin` failed because this environment is mounted read-only and can’t write under `.meridian/spawns/...`. Here is the full report markdown for fallback extraction:

---

# agent-shell-mvp — design convergence verification (Decisions D1–D20)

VERDICT: **NEARLY-CONVERGED**

Convergence pass resolves the prior **BLOCKER** set and the convergent **MAJOR** items, but a few residual cross-doc drifts remain (mostly legacy `/workspace/...` paths and one V0/V1 scope leak).

## Prior BLOCKER / MAJOR re-check (confirmation)

1. **SOLID BLOCKER-1 (canonical normalized event schema)** — **Resolved**
   - `design/harness-abstraction.md` §4 declares the **canonical normalized schema** and explicitly states other docs derive from it.
   - `design/event-flow.md` states `harness-abstraction.md` is canonical and treats wire as a thin rename layer.
   - `design/frontend-protocol.md` §1/§11 explicitly points to canonical normalized schema in `harness-abstraction.md`.

2. **SOLID BLOCKER-2 (`submit_tool_result` path)** — **Resolved**
   - `design/harness-abstraction.md` adds `HarnessSender.submit_tool_result(...)` and the `SubmitToolResult` normalized command.
   - `design/event-flow.md` tool execution path resumes the harness via `submit_tool_result(...)` (router/orchestrator does not emit Claude-specific frames).

3. **Alignment BLOCKER-1 (interactive tool execution contradiction)** — **Resolved**
   - `design/interactive-tool-protocol.md` chooses backend-owned subprocess runner + file handoff.
   - `design/local-execution.md` §12 matches: interactive tools are subprocesses owned by `ToolExecutionCoordinator`, not in-kernel.

4. **Alignment BLOCKER-2 (upload/staging contradiction)** — **Resolved**
   - `design/frontend-protocol.md` §10 and `design/local-execution.md` §9 converge on V0 multipart upload to `<work-item>/data/raw/<dataset_name>/`.
   - `design/event-flow.md` uses the same “files live in work item dir” story, with one residual legacy example noted below.

5. **Alignment BLOCKER-3 (session semantics contradiction)** — **Resolved**
   - `design/frontend-protocol.md` §2.4 defines V0 reconnect: 30s replay window else `SESSION_RESYNC`.
   - `design/event-flow.md` and `design/frontend-integration.md` describe multi-tab behavior as shared-session fan-out + `agent_busy` on concurrent sends.

6. **Refactor #1 (module home split)** — **Resolved**
   - `design/repository-layout.md` commits the single home at `src/meridian/shell/`.
   - `design/harness-abstraction.md` references `src/meridian/shell/schemas/*` and `src/meridian/shell/adapters/*`.

7. **Refactor #2 (EventRouter doing too much)** — **Resolved**
   - `design/repository-layout.md` and `design/event-flow.md` show the split: `router.py` (fan-out), `turn.py` (turn lifecycle), `tools/coordinator.py` (tool execution).

8. **Capability flag honesty (SOLID MAJOR-3)** — **Resolved**
   - `design/harness-abstraction.md` defines `supports_*` and sets Claude V0 effective values (`supports_mid_turn_injection=false`, `supports_session_persistence=false`, etc.), with explicit rationale.
   - `design/frontend-protocol.md` `SESSION_HELLO.capabilities` matches.

9. **Naming canonicalization (D12)** — **Resolved**
   - `design/harness-abstraction.md` normalized layer uses `turn_id`, `tool_call_id`, `result_kind`.
   - `design/event-flow.md` explicitly calls out “never `run_id` / `resultType` in normalized layer”.
   - `design/frontend-protocol.md` wire layer uses `turnId`/`toolCallId`/`resultKind` and `supports_*` capability flags.

## Decision verification matrix (D1–D20)

| Decision | Expected change | Observed in docs? | Gap |
|---|---|---|---|
| D1 | Canonical normalized event schema in `harness-abstraction.md`; others derive | Yes | `interactive-tool-protocol.md` §8 still cites legacy `/workspace/.meridian/meshes/...` contract; should instead reference the canonical work-item paths described in `local-execution.md` and the `.meridian/interactive_inputs/...` handoff (see Residual #1) |
| D2 | Add `HarnessSender.submit_tool_result(...)`; orchestration uses it | Yes | None |
| D3 | Capability flags reflect **effective** V0 behavior (honest `supports_*`) | Yes | None |
| D4 | Shell code “home” is `src/meridian/shell/` (session + adapters + schemas) | Yes | None |
| D5 | Split `EventRouter` → `EventRouter` + `TurnOrchestrator` + `ToolExecutionCoordinator` | Yes | None |
| D6 | Interactive tools run as subprocess via coordinator; file handoff under work item | Mostly | Cross-doc drift on *where meshes live*: `local-execution.md` stores meshes under per-turn cell directories; `interactive-tool-protocol.md` §8 still claims a global `/workspace/.meridian/meshes/...` path (Residual #1) |
| D7 | One global analysis venv `~/.meridian/venvs/biomedical/` managed by `uv` | Yes | None |
| D8 | V0 ingest = drag-drop multipart to `<work-item>/data/raw/<dataset_name>/` | Mostly | `event-flow.md` tool-error example still references `/workspace/data/raw/...` (Residual #2) |
| D9 | V0 session = one backend process bound to one work item; 30s reconnect buffer | Mostly | `frontend-integration.md` still lists `/api/work-items` endpoints as a V0 surface; either mark as V1-only or remove to match “no left-rail work-item picker in V0” (Residual #3) |
| D10 | Claude init uses `--append-system-prompt` + `--mcp-config` (no stdin init frame) | Yes | None |
| D11 | Path A (vision self-feedback) is V0 (plain `python` + images) | Yes | None |
| D12 | Canonicalize names: `supports_*`, `turn_id`, `tool_call_id`, `result_kind` | Yes | Minor: `frontend-protocol.md` uses `/workspace/...` in an example tool command; consider swapping to `$MERIDIAN_WORK_DIR/...` to avoid reintroducing the old mental model |
| D13 | Mid-turn injection deferred to V1; keep abstract method; V0 raises `CapabilityNotSupported` | Yes | None |
| D14 | Tool approval gating deferred to V1; V0 runs `bypassPermissions` | Yes | None |
| D15 | Session persistence deferred to V1; V0 drop-on-restart | Yes | None |
| D16 | No-terminal launcher deferred; V0 is developer-mediated launch + bookmark | Yes | None |
| D17 | No Pydantic↔TS codegen in V0; hand-maintained types + parity tests | Yes | None |
| D18 | Ship prebuilt `frontend/dist` in releases; pnpm dev-only | Yes | None |
| D19 | Cut Yjs collab; keep CM6 drafting + localStorage autosave | Yes | None |
| D20 | Path A/B mode is agent+skill responsibility, not shell state | Yes | None |

## Residual issues

1. **Legacy `/workspace` path drift in interactive-tool + mesh storage story**
   - `design/interactive-tool-protocol.md` §3.2 and §8 still claim `show_mesh()` writes meshes under `/workspace/.meridian/meshes/{mesh_id}.bin`.
   - `design/local-execution.md` §13 (audit layout) places meshes under `<work-item>/.meridian/turns/<turn_id>/cells/<cell_id>/meshes/<mesh_id>.bin`.
   - `design/interactive-tool-protocol.md` §3.4 correctly describes the V0 handoff contract via `<work-item>/.meridian/interactive_inputs/<tool_call_id>/...` and `interactive_results/<tool_call_id>.json`.
   - Net: `interactive-tool-protocol.md` is internally inconsistent and drifts from `local-execution.md`. This is a clarity risk for implementers.

2. **Legacy `/workspace` in `event-flow.md` tool error envelope**
   - `design/event-flow.md` §8.1 error example uses `"No such file: /workspace/data/raw/femur.dcm"`.
   - `design/local-execution.md` §7 and §9 establish `$MERIDIAN_WORK_DIR/data/raw/...` and `<work-item>/data/raw/...` as the V0 truth.

3. **V0/V1 scope leak: work-item list endpoints**
   - `design/frontend-integration.md` §5.1 lists `work-items.ts` and calls out “work items list” as a REST-fed surface.
   - `decisions.md` D9 explicitly removes the V0 “left rail of work items” / multi-work-item routing.
   - Suggestion: keep the file as a V1 placeholder but label it V1-only, or remove from the V0 surface list to avoid reintroducing the deferred UI.

## Recommended next action

- Apply a tiny follow-up convergence edit to:
  - `design/interactive-tool-protocol.md` (replace `/workspace/.meridian/meshes/...` with work-item-relative paths and align the mesh handoff story with the `.meridian/interactive_inputs/...` contract and `local-execution.md`’s audit layout),
  - `design/event-flow.md` (fix the tool error example path),
  - `design/frontend-integration.md` (clarify `/api/work-items` as V1-only or delete from the V0 “Surface” list).
- After edits, re-run a quick `rg "/workspace/" .meridian/work/agent-shell-mvp/design/*.md` sweep to ensure remaining `/workspace` mentions are explicitly framed as “legacy biomed-mvp had …” and not presented as V0 truth.
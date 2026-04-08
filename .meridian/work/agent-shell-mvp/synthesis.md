# agent-shell-mvp — Design Synthesis

**Status:** Design converged after follow-up correction pass (p1135) applying `findings-harness-protocols.md`. Ready for user review of open questions, then hand off to `@planner`.

> **Correction pass (2026-04-08).** Three structural assumptions in the original convergence pass were corrected against `findings-harness-protocols.md`:
>
> 1. **All three harnesses are tier-1.** Codex `app-server` exposes a stable JSON-RPC 2.0 stdio protocol with `turn/start` + `turn/interrupt` per developers.openai.com/codex/app-server. Earlier framing of codex as "experimental / deferred / TBD" is wrong and has been removed from harness-abstraction.md, overview.md, and repository-layout.md.
> 2. **Codex is V1-capable, not V2/deferred.** Implementation order between codex and opencode is now a product decision (whichever customer/use case shows up next), not a protocol-risk decision.
> 3. **Mid-turn steering is tier-1, V0-scope.** `HarnessSender.send_user_message()` and `inject_user_message()` are core methods implemented by every adapter from day one. The frontend protocol models mid-turn input as a first-class event, and `meridian spawn inject <spawn_id>` ships as a V0 CLI command. Capability semantics surface as a semantic enum (`queue` / `interrupt_restart` / `http_post` / `none`), not a boolean.
>
> The previous Q2 recommendation (defer mid-turn injection to V1) is **superseded** by Q6 below. The infrastructure cost is the same — the HarnessAdapter layer is being built either way — and mid-turn steering is the differentiating capability of the platform.

**Scope:** Amalgamate meridian-channel (CLI substrate + harness adapters), meridian-flow `biomedical-mvp` (persistent kernel, tool execution, result capture), and meridian-flow `frontend-v2` (React chat + editor) into a single domain-flexible local agent shell. V0 validates with the Yao Lab μCT pipeline ("Dad's use case").

---

## 1. What the design committed to

Authoritative artifacts (all in `$MERIDIAN_WORK_DIR/`):

- `requirements.md` — contract (10 decisions + Q1–Q5 + non-goals)
- `decisions.md` — 20 concrete design decisions D1–D20 with rationale and alternatives
- `design/overview.md` — system topology, component map, data flow, V0/V1 fence
- `design/harness-abstraction.md` — **load-bearing.** Canonical normalized event schema, SOLID protocol split (`HarnessLifecycle`/`HarnessSender`/`HarnessReceiver`/`HarnessCapabilities`), ClaudeCode V0 + OpenCode V1 sketches
- `design/event-flow.md` — turn lifecycle, tool execution via `submit_tool_result`, reconnect/resync semantics
- `design/frontend-protocol.md` — WebSocket wire events, SESSION_HELLO capabilities, hand-maintained TS+Python types
- `design/agent-loading.md` — `SessionContext` under `src/meridian/shell/`, reuses existing `compose_run_prompt`/`load_agent_profile`/`SkillRegistry`, Claude init via `--append-system-prompt` + `--mcp-config`
- `design/interactive-tool-protocol.md` — Path B: subprocess-owned PyVista runners, file handoff via `.meridian/interactive_inputs/<tool_call_id>/`
- `design/repository-layout.md` — `src/meridian/shell/` home, top-level `frontend/`, prebuilt `frontend/dist` in releases
- `design/frontend-integration.md` — frontend-v2 copy strategy with explicit cut list (Yjs collab/transport/session out; CM6 core in)
- `design/local-execution.md` — jupyter_client persistent kernel, separate biomedical venv at `~/.meridian/venvs/biomedical/`, per-turn audit layout

### Key structural decisions

1. **D1** — Canonical normalized event schema lives in `harness-abstraction.md`; wire protocol is a thin rename layer.
2. **D2** — `HarnessSender.submit_tool_result(...)` is a first-class protocol method. Orchestrator never emits Claude-specific frames.
3. **D3** — Capabilities are **effective** declarations. `mid_turn_injection` is a semantic enum (`queue` / `interrupt_restart` / `http_post` / `none`) so the UI can render the right per-harness affordance instead of a binary flag. Other capabilities remain `supports_*` flags. No lies in the abstraction. *(Updated by p1135: see `findings-harness-protocols.md` §1.)*
4. **D4** — All shell code under `src/meridian/shell/` (session, adapters, schemas, router, turn, tools/coordinator, runtime).
5. **D5** — `EventRouter` split into `EventRouter` (fan-out) + `TurnOrchestrator` (turn lifecycle) + `ToolExecutionCoordinator` (tool dispatch).
6. **D6** — Interactive tools are backend-spawned subprocesses with file handoff. Not in-kernel. Not a second mars registry.
7. **D7** — Single global biomedical venv at `~/.meridian/venvs/biomedical/` managed by `uv`; keeps SimpleITK/VTK out of meridian-channel's project venv.
8. **D8** — V0 DICOM ingest = drag-drop multipart into `<work-item>/data/raw/<dataset>/`. No presign, no finalize.
9. **D9** — Single backend process bound to one work item. 30s reconnect buffer; `SESSION_RESYNC` on overflow. Multi-tab = fan-out to same session.
10. **D10** — Claude init uses `--append-system-prompt` + `--mcp-config` only. No stdin init frame, no two-path init.
11. **D12** — Normalized names: `turn_id`, `tool_call_id`, `result_kind`, `supports_*`. Wire layer renames to camelCase. Never `run_id`/`resultType` in the abstraction.
12. **D17** — No Pydantic↔TS codegen in V0. Hand-maintained types + parity test.
13. **D18** — Ship prebuilt `frontend/dist` in releases. `pnpm` is dev-only.
14. **D19** — Cut Yjs collab editor. Keep CM6 + localStorage autosave.
15. **D20** — Path A vs Path B mode selection is agent+skill responsibility, not shell state.

### Review convergence

Four independent reviews ran in parallel on diverse models (gpt-5.4, gpt-5.2, opus-4.6):

- **solid-review.md** — 2 BLOCKERs (canonical schema, submit_tool_result path) → both resolved (D1, D2).
- **alignment-review.md** — 4 BLOCKERs (interactive exec, upload staging, session semantics, no-terminal) → 3 resolved (D6, D8, D9); no-terminal launcher deferred to V1 (D16, flagged as open question).
- **refactor-review.md** — 3 High findings (module home split, EventRouter overloaded, tool registry mismatch) → all resolved (D4, D5, D6).
- **feasibility-review.md** — surfaced install burden + 8–12 week realistic timeline; translated into explicit implementation-phase risks (below).
- **convergence-verification.md** — verdict **NEARLY-CONVERGED**; 3 small residual drifts (legacy `/workspace` paths, `/api/work-items` V0 leak) now patched. Final grep sweep clean.

---

## 2. What the user still needs to answer

The design surfaces these for **user decision** — do not treat the recommendations as final.

### Q1 — Relationship to `meridian-flow`
**Status:** Open. Design does not resolve.
**Recommendation:** (c) **Replace eventually.** meridian-flow's biomedical-mvp and frontend-v2 are the lineage sources for this shell. Once agent-shell-mvp lands, meridian-flow's role collapses to archive. No V0 dependency on meridian-flow runtime.
**Needs from user:** confirm direction so @planner doesn't plan any coexistence bridges.

### Q2 — V0 scope: mid-turn injection, permission gating, session persistence
**Status:** Mid-turn portion **superseded by Q6**. Permission gating and session persistence remain V1.
**Recommendation:**
- **Mid-turn injection → V0.** *(Reversed from prior recommendation per `findings-harness-protocols.md`.)* Claude Code's stream-json supports `user` NDJSON queue-to-next-turn; codex `app-server` supports `turn/interrupt`+`turn/start`; opencode supports HTTP POST. All three are tier-1 capable. The HarnessAdapter is being built either way — implementing `send_user_message()` and `inject_user_message()` honestly from day one is cheaper than retrofitting later, and mid-turn steering is the differentiating product feature. See Q6.
- **Tool approval gating → V1.** V0 runs `bypassPermissions` (Dad is trusted local user). UI placeholder only.
- **Session persistence → V1.** V0 is drop-on-restart. Work item dir + files-as-authority gives enough reproducibility without session replay.
**Needs from user:** approve the V1 deferrals for the remaining two; confirm Q6 to lock in mid-turn V0.

### Q3 — Repository layout
**Status:** **Resolved in design.** `src/meridian/shell/` + top-level `frontend/`. See `repository-layout.md`.

### Q4 — frontend-v2 cuts
**Status:** **Resolved in design.** See `frontend-integration.md` cut list. Yjs collab/transport/persistence/session out; CM6 core + activity-stream reducer + WS client in.

### Q5 — Mid-turn design shape (opencode vs Claude)
**Status:** **Resolved in design, refined by p1135.** Abstraction is shaped against the stable mid-turn primitives of all three harnesses. `HarnessCapabilities.mid_turn_injection` is a semantic enum (`queue` for Claude, `interrupt_restart` for codex, `http_post` for opencode, `none` only as a fallback); the UI renders a different affordance per value rather than a binary "supported / not". When codex or opencode lands the value flips without changing router/translator code.

### Q6 — Mid-turn steering: tier-1 V0 or defer to V1? *(NEW — added by p1135)*
**Status:** Open. **Strong recommendation: tier-1 V0.**
**Why:** The HarnessAdapter layer is being built either way. `send_user_message()` and `inject_user_message()` are protocol-stable on all three harnesses (Claude `user` NDJSON queue, codex `turn/interrupt`+`turn/start`, opencode `POST /session/:id/prompt_async`). Retrofitting mid-turn semantics into a finalized adapter interface costs more than wiring it correctly from day one. More importantly, mid-turn steering is the **differentiating capability** of the platform vs. every other "chat UI over Claude Code" — it's what lets a user (or a parent orchestrator) course-correct a running agent instead of killing and respawning. Shipping V0 without it means shipping the same product everyone else is building.
**Cost of V0:** ~1 phase of additional adapter wiring + frontend composer enable mid-turn + `meridian spawn inject <spawn_id>` CLI command. Smoke test exercises all three modes at the abstraction layer (Claude V0 adapter is the only one tested live; codex/opencode use a fake until their adapters land, but the contract is exercised).
**Cost of deferral to V1:** infrastructure cost is similar but the abstraction has to be revisited to make sure the lifecycle/contract didn't bake in single-direction assumptions. Bigger risk than the V0 path.
**Needs from user:** explicit yes/no.

### Q7 — Should `meridian spawn` route through the HarnessAdapter? *(NEW — added by p1135)*
**Status:** Open. **Strong recommendation: yes.**
**Why:** Today `meridian spawn` shells out via the single-shot adapters in `src/meridian/lib/harness/`. The shell will build a session-lived `HarnessAdapter` family in `src/meridian/shell/adapters/`. If `meridian spawn` is migrated onto the same adapter layer, every spawn in the dev-orchestration tree gains a mid-turn control channel for free — `meridian spawn inject <spawn_id> "reconsider X"` becomes harness-agnostic, and dev-orchestrators can steer their children programmatically using the same primitive the UI uses. This is the **amalgamation move**: meridian-channel (CLI substrate) and the agent-shell (UI) consume the *same* adapter layer instead of each owning their own. Two consumers, one mechanism.
**What this isn't:** a rewrite of `meridian spawn` semantics. The spawn registry, session JSONL store, and report extraction stay. Only the harness-launching/IO layer changes — single-shot adapters in `lib/harness/` are deprecated in favor of session-lived adapters in `shell/adapters/`, and the spawn lifecycle wraps "create adapter → run one turn → tear down" if no caller injects.
**Cost:** moderate. Single-shot adapters and session adapters share concepts, not code; a unification step trades two adapter families for one. Worth it because (a) it unlocks mid-turn steering for dev-orchestrators *today*, and (b) it removes the long-term "two harness layers, slowly drifting" maintenance burden.
**Risks:** the existing single-shot adapters' assumptions (process exits, report file written on stop) need a thin compatibility wrapper while the session-adapter family stabilizes. Worst case: keep both for one release cycle and migrate spawn callers incrementally.
**Needs from user:** explicit yes/no/defer.

### Additional decisions surfaced during design

- **D16 — No-terminal launcher:** V0 is developer-mediated (`meridian shell start` from terminal). Violates the strict "Dad never touches terminal" clause in requirements.md. **Needs user call:** accept as V0 limitation (developer starts for Dad) or fund a real launcher bundle now (+2–3 weeks).
- **Install burden (feasibility-review):** Realistic V0 prereqs = Python 3.12+, `uv`, biomedical venv, Claude Code CLI + auth, `mars sync`, display stack for PyVista. Design assumes a bootstrap command will paper over this; that command does not yet exist. **Needs user call:** accept developer-mediated install for V0, or fund a bootstrap installer.

---

## 3. Recommended implementation phase sketch

The @planner should decompose this into ordered phases. Suggested shape — not prescriptive:

### Phase 1 — Shell skeleton (no harness, no frontend)
- `src/meridian/shell/` package scaffolding per `repository-layout.md`
- `SessionContext`, `meridian shell start` CLI subcommand
- FastAPI backend with placeholder `/ws` echo
- Reuse `resolve_policies`/`load_agent_profile`/`SkillRegistry`/`compose_run_prompt`
- **Exit:** `meridian shell start --profile data-analyst` boots, holds a session, logs an empty turn

### Phase 2 — Harness abstraction + Claude V0 adapter
- Normalized event schema (Pydantic) per `harness-abstraction.md` §4
- `HarnessLifecycle` / `HarnessSender` / `HarnessReceiver` / `HarnessCapabilities` protocols
- `ClaudeCodeAdapter` (stream-json subprocess, `--append-system-prompt` + `--mcp-config`)
- `EventRouter` / `TurnOrchestrator` / `ToolExecutionCoordinator` split
- **Exit:** backend can run a Claude turn and return events over WS in normalized shape
- **Risk:** stream-json reverse-engineering. Phase 2 must include a stream-json parity test harness.

### Phase 3 — Frontend copy + activity stream
- Copy frontend-v2 per `frontend-integration.md` cut list
- New API client + WS client (hand-typed)
- Activity stream reducer wired to normalized wire events
- SESSION_HELLO + capability-driven UI gating
- `pnpm build` → `frontend/dist/` committed to releases
- **Exit:** chat works end-to-end against Claude V0

### Phase 4 — Persistent Python kernel + tool execution
- `ToolExecutionCoordinator` with jupyter_client kernel
- `result_helper` injection (show_plotly/show_matplotlib/show_dataframe/show_mesh)
- Per-turn audit layout under `<work-item>/.meridian/turns/<turn_id>/cells/<cell_id>/`
- `DISPLAY_RESULT` wire events
- **Exit:** Claude can run python code and frontend shows plots + dataframes

### Phase 5 — Biomedical venv + ingest
- `~/.meridian/venvs/biomedical/` bootstrap (SimpleITK, VTK, PyVista, numpy, scipy)
- V0 drag-drop multipart to `<work-item>/data/raw/<dataset>/`
- Dataset browser in sidebar
- data-analyst → biomedical agent profile (requires the real biomedical skill corpus — flagged high-risk by feasibility review)
- **Exit:** Dad can drag in a DICOM folder and Claude can load it

### Phase 6 — Interactive tools (Path B)
- `InteractiveToolRegistry` + subprocess runner
- File handoff contract under `.meridian/interactive_inputs/<tool_call_id>/`
- V0 tools: `pick_points_on_mesh`, `pick_box_on_volume`, `pick_threshold_on_histogram`, `orient_with_pca_preview`
- Mesh viewer in frontend (react-three-fiber, passive)
- **Exit:** landmark correction works on a real bone mesh

### Phase 7 — Golden-dataset smoke + biomedical skill corpus
- Automated smoke: DICOM load → segment → mesh display → one landmark correction
- Write the biomedical skill corpus (the weakest link per feasibility review)
- Path A prompt patterns (vision self-feedback)
- **Exit:** Dad can run the full 10-step μCT pipeline unsupervised

### V1 (post-validation)
- OpenCode adapter (HTTP/ACP) + flip capability flags
- Codex `app-server` adapter (JSON-RPC stdio), including shell-owned tool
  bridge via MCP (see harness-abstraction §9.5.1)
- Permission gating, session persistence (Claude resume by captured session id)
- No-terminal launcher bundle
- Work-item picker / multi-work-item routing
- **Phase V1-Q7: route `meridian spawn` through the session HarnessAdapter
  family.** Not trivial. Today, `meridian spawn` is single-shot (process
  exits → read `report.md`); session adapters are event-streamed
  (stdout notifications, lifecycle `start`/`interrupt`/`finish`). Every
  dev-orchestration caller (planner/coder/reviewer/verifier) currently
  depends on the single-shot contract transparently. Unifying requires:
  (a) a "single-shot over session adapter" shim that blocks until a
  `RunFinished` event and writes a synthesized `report.md`; (b) rethinking
  `spawn wait` semantics; (c) a compatibility pass across the entire
  dev-orchestration caller set. Scope this as a dedicated V1 phase, not
  a line item inside another phase. See Q7 for the motivation.

### Parallelism opportunities for @planner
- Phase 3 (frontend) can start in parallel with Phase 2 (backend harness) once the wire protocol is frozen at end of Phase 1.
- Phase 5 (biomedical venv bootstrap) can start in parallel with Phase 4 (kernel wiring).
- Phase 6 (interactive tools) depends on Phase 4 and Phase 5.

### Recommended staffing for @planner
- **@planner** (opus) — phase decomposition from this design
- **@coder** (gpt-5.3-codex) — primary implementer for each phase
- **@verifier + @smoke-tester** — per-phase lane
- **@browser-tester** — Phase 3 onward
- **@reviewer fan-out** — only at end-of-phase escalation and final review loop (gpt-5.4 / gpt-5.2 / opus with diverse focus areas, plus @refactor-reviewer)

---

## 4. Residual risks to carry into implementation

1. **Claude stream-json is partly reverse-engineered, including the Q6 mid-turn `queue` mode.** Phase 2 must budget for protocol discovery and build a parity test harness early. **Phase 1.5 verification spike (added by p1135 review):** before locking Q6 as V0, run a one-day spike on a real `claude --input-format stream-json` subprocess that exercises (a) `-p ""` + first NDJSON handshake, (b) writing a second `user` NDJSON line during a tool-call streaming window, (c) writing a `user` NDJSON line during text streaming. If any leg fails, ClaudeCodeAdapter ships V0 with `mid_turn_injection="none"` instead of `"queue"` — the abstraction still holds, but the V0 composer affordance flips to disabled-mid-turn until codex or opencode lands. The Phase 1.5 spike protects Q6 from being cargo-culted from companion's reverse-engineering.
2. **Biomedical skill corpus is the product, not the plumbing.** The current `data-analyst` profile is a thin persona. Phase 7 is the actual validation bottleneck.
3. **PyVista/VTK stability over long sessions is assumed.** Add explicit crash-recovery paths in Phase 6.
4. **No-terminal launcher deferred.** Dad's first session will be developer-mediated. Revisit after Phase 7.
5. **Install burden.** Bootstrap command must land before external handoff.

---

## 5. Next step

Hand off to **@planner** with:
- `$MERIDIAN_WORK_DIR/design/` — all 10 design docs
- `$MERIDIAN_WORK_DIR/decisions.md` — D1–D20
- `$MERIDIAN_WORK_DIR/synthesis.md` — this doc
- `$MERIDIAN_WORK_DIR/reviews/` — review trail for context

Before that, the user should confirm or override the open questions in §2 (especially Q2 deferrals and D16 no-terminal acceptance) so the plan doesn't need to be re-cut.

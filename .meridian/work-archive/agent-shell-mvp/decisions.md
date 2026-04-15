# agent-shell-mvp — design phase decision log

Decisions made during the design phase. The 10 architectural inputs from `requirements.md` are not re-litigated here — see that file for the contract. Decisions captured below are the ones the design phase made on top of the contract.

## D1 — Use one canonical normalized event schema; wire docs derive from it

**Date:** 2026-04-08  
**Trigger:** Convergent BLOCKER from SOLID review and refactor review — `harness-abstraction.md`, `frontend-protocol.md`, and `event-flow.md` describe overlapping but inconsistent event vocabularies (`turnId` vs `runId`, `displayId` missing in normalized layer, `resultType` vs `resultKind`, `status:"ok"` vs `status:"done"`, 3-event vs 5-event thinking family).

**Decision:** The canonical contract is the **normalized event schema** in `harness-abstraction.md`. All other docs (`frontend-protocol.md`, `event-flow.md`, `interactive-tool-protocol.md`, `agent-loading.md`) reference and derive from it. The translator becomes a thin rename/wrap layer in V0 — no field synthesis, no lifecycle reconstruction. If the wire format needs a field the normalized layer doesn't have, the field is added to the normalized layer first.

**Why:** SOLID review BLOCKER-1 — without one canonical schema, the translator inevitably accumulates per-harness special cases, which is exactly the abstraction leak the design promises to avoid.

**Rejected alternative:** Derive the normalized layer from the wire format. Rejected because the wire format is currently shaped by frontend-v2/biomedical-mvp legacy and is not LCD across harnesses.

## D2 — Add an explicit `submit_tool_result` path to `HarnessSender`

**Date:** 2026-04-08  
**Trigger:** SOLID review BLOCKER-2 — locally executed tool results (python tool, interactive tools) need to flow back into the harness so the agent's turn can continue. The current design has the EventRouter writing Claude-specific `tool_result` NDJSON on stdin, which leaks Claude shape into the router and breaks DIP/OCP.

**Decision:** Add `HarnessSender.submit_tool_result(tool_call_id, result_payload, status)` as a first-class normalized command. Each adapter implements it harness-natively (Claude: stream-json `tool_result` frame on stdin; OpenCode: HTTP POST `/session/{id}/tool_result`). The router calls the abstract method only.

**Why:** The tool execution loop is the most important seam after the event stream itself. Leaking it breaks the abstraction at the highest-leverage spot.

## D3 — Capability flags describe **effective** behavior, not theoretical harness potential

**Date:** 2026-04-08  
**Trigger:** SOLID review MAJOR-3, refactor review #5. `ClaudeCodeAdapter.capabilities` advertises `mid_turn_injection=True`, `session_persistence=True`, etc., but `event-flow.md` and `frontend-protocol.md` document V0 as not supporting any of those.

**Decision:** Capability flags describe **what the adapter actually does in this build**. If V0 Claude adapter doesn't implement mid-turn injection, the flag is `False` regardless of whether stream-json could in principle support it. When V1 implements it, the flag flips to `True`. Frontend gates UI affordances on the effective flags.

**Rejected alternative:** Split into `protocol_supports_X` and `enabled_X`. Rejected as over-engineering; one honest flag is enough.

## D4 — `SessionContext` lives in `src/meridian/shell/session.py`; harness adapters in `src/meridian/shell/adapters/`

**Date:** 2026-04-08  
**Trigger:** Refactor review #1 — the design tree is split across `backend/`, `src/meridian/shell/`, and `src/meridian/lib/` in different docs. "New harness = one file + registration" can't hold if the home isn't decided.

**Decision:** All shell-related code lives under `src/meridian/shell/`. Specifically:
- `src/meridian/shell/session.py` — SessionContext, session lifecycle
- `src/meridian/shell/adapters/{base.py, claude_code.py, opencode.py}` — harness adapters
- `src/meridian/shell/translator.py` — wire ↔ normalized translator
- `src/meridian/shell/router.py` — EventRouter (now a thin pass-through, see D5)
- `src/meridian/shell/turn.py` — TurnOrchestrator (split from EventRouter, see D5)
- `src/meridian/shell/runtime/` — local kernel, exec service
- `src/meridian/shell/tools/` — interactive tool registry + V0 PyVista tools
- `src/meridian/shell/schemas/` — pydantic models

`src/meridian/lib/harness/` (the existing single-shot adapters) is **untouched**. The session-lived adapters are a new tree under `shell/adapters/`. They share concepts but not code.

`agent-loading.md` reuses the **existing** `compose_run_prompt`, `load_agent_profile`, `SkillRegistry` from `src/meridian/lib/agent/` — those functions stay where they are; `SessionContext` calls them from `src/meridian/shell/session.py`.

## D5 — Split `EventRouter` into router + `TurnOrchestrator` + `ToolExecutionCoordinator`

**Date:** 2026-04-08  
**Trigger:** Refactor review #2. The design says "EventRouter just routes" but the flow shows it intercepting tool calls, executing them locally, emitting display results, and feeding results back to the harness. That's three concerns.

**Decision:** Three modules:
- `router.py` — `EventRouter` is genuinely dumb: takes a normalized event, decides which sink (frontend WS, persistence, audit log) to send it to. No tool interception, no orchestration.
- `turn.py` — `TurnOrchestrator` owns one user turn's lifecycle. Receives `RunStarted` to `RunFinished`, knows the turn id, coordinates with `ToolExecutionCoordinator` when a tool call needs local execution.
- `tools/coordinator.py` — `ToolExecutionCoordinator` knows how to execute a normalized tool call (python, bash, interactive) against the runtime, capture the result, and submit it back via `HarnessSender.submit_tool_result()`.

Each is independently testable.

## D6 — Interactive tools run as subprocess invoked by `ToolExecutionCoordinator`, NOT inside the persistent kernel

**Date:** 2026-04-08  
**Trigger:** Convergent BLOCKER (alignment BLOCKER-1, feasibility High #2). `interactive-tool-protocol.md` chose subprocess; `local-execution.md` flipped to in-kernel. They contradicted.

**Decision:** Interactive tools run as **separate subprocesses** spawned by `ToolExecutionCoordinator`. Rationale:
- PyVista needs its own event loop and display surface; kernel blocking is fragile
- Cancellation is clean: `SIGTERM` the subprocess; kernel keeps state
- The kernel stays available for parallel python tools (it doesn't, in V0, but the constraint is cleaner)
- Mesh data is handed off via files in `<work-item>/.meridian/interactive_inputs/<tool_call_id>/` (the kernel writes mesh bytes there before invoking the interactive tool)
- File-based handoff matches files-as-authority discipline (Decision 9)

`local-execution.md` is updated to reflect this — its §12 contradicting recommendation is removed.

**Cost:** mesh round-trips through disk for every interactive picking call. Acceptable for V0; meshes are small enough.

## D7 — One global analysis venv at `~/.meridian/venvs/biomedical/`, managed by uv

**Date:** 2026-04-08  
**Trigger:** Feasibility review medium #4 — `local-execution.md` says one global venv, `repository-layout.md` says project-level `uv sync --extra biomedical`. Dad cannot debug which environment owns SimpleITK.

**Decision:** The biomedical analysis venv is **separate from** the meridian-channel project venv. It lives at `~/.meridian/venvs/biomedical/` (or platform equivalent), is created by `meridian shell init biomedical` on first run, and is the only venv the kernel uses. The project venv (where `meridian` itself runs) does NOT contain SimpleITK/PyVista/etc. — those are too heavy and too domain-specific to bundle into the meridian package.

This means biomedical packages are NOT in `pyproject.toml --extra biomedical`. They are in a separate manifest at `src/meridian/shell/runtime/manifests/biomedical.toml` (or similar) that `meridian shell init` reads. New domains add a new manifest file; `meridian shell init <domain>` provisions a new venv.

This also fixes refactor review #6 — biomedical specifics no longer leak into the core shell pyproject.

## D8 — V0 DICOM ingest = drag-drop into `<work-item>/data/raw/<dataset_name>/`, no presign/manifest dance

**Date:** 2026-04-08  
**Trigger:** Alignment review BLOCKER-2. Three docs disagreed on upload model.

**Decision:** V0 has **one** ingest path: a drag-drop zone in the frontend that POSTs multipart to a simple `POST /api/datasets/<name>` backend endpoint. The backend writes bytes directly to `<work-item>/data/raw/<dataset_name>/`. No presign, no finalize, no classify, no manifest. A sidebar `DatasetBrowser` component shows what's landed. The agent's `python` tool can read those files directly via `pydicom`.

`local-execution.md` §9 already documents this; `frontend-integration.md` §5.1 and `frontend-protocol.md` §10 are updated to match.

V1 may add the biomedical-mvp upload pipeline (presign/finalize/classify) if validation surfaces a need. V0 trusts the local filesystem.

## D9 — Single session per process, single tab, work item identity = process

**Date:** 2026-04-08  
**Trigger:** Alignment BLOCKER-3, refactor #4.

**Decision:** V0 session model is the simplest possible:
- `meridian shell start --work-item <name>` launches one backend bound to one work item.
- The work item directory IS the session identity. There is no separate `session_id` in V0 (a synthetic one is generated for wire compatibility but unused).
- Browser opens to the single shell. Multi-tab = same session, fan-out events to all connected sockets, last command wins. No isolation.
- WS disconnect: backend buffers events in memory for 30 seconds. Reconnect within window replays buffered events from last seen sequence number. After 30s, stale events are dropped; reconnect gets a `SESSION_RESYNC` event with current state digest.
- Server restart = session lost. V0 explicit non-goal: cross-process persistence.

To switch work items, restart the backend. `meridian shell start --work-item <other>` is a new process. This is intentional V0 simplification.

Multi-work-item routing in `frontend-integration.md` is **removed** for V0. The "left rail of work items" UI is deferred to V1.

## D10 — Claude Code init: use `--append-system-prompt` + `--mcp-config` for tools, NOT init stream-json frame

**Date:** 2026-04-08  
**Trigger:** SOLID MAJOR-4 — `agent-loading.md` and `harness-abstraction.md` described two different Claude init paths.

**Decision:** Claude Code adapter launches the subprocess with:
- `--append-system-prompt` — composed system prompt from `SessionContext`
- `--mcp-config` — JSON config file describing the tools (python, bash, etc.) the agent can call (Claude Code uses MCP for tool surfaces)
- `--permission-mode bypassPermissions` for V0 (we wrap permissions at the shell layer, not Claude's)
- `--input-format stream-json --output-format stream-json` for the bidirectional channel
- working directory = work item dir

Then the first `user` stream-json frame on stdin starts the conversation. **No** init system prompt frame (the `--append-system-prompt` flag handles it).

`agent-loading.md` is updated to describe `compose_run_prompt` output flowing into `--append-system-prompt`. `harness-abstraction.md` ClaudeCodeAdapter section is updated to match.

## D11 — Path A (vision self-feedback) is V0, just normal `python` + `show_image` + multimodal context

**Date:** 2026-04-08  
**Trigger:** Alignment MAJOR-3 — `overview.md` listed Path A under V1, `interactive-tool-protocol.md` described it as already-V0.

**Decision:** Path A IS V0. It is not a new tool or protocol — it's the agent calling the existing `python` tool to render a mesh to a PNG, then the next assistant turn includes the image in its context (Claude Code natively supports image inputs). No new shell mechanism. `overview.md` Path A claim is corrected to V0.

## D12 — Naming canonicalization

**Date:** 2026-04-08  
**Trigger:** Refactor review #5 — `mid_turn_injection` vs `supports_mid_turn_injection`, `SessionContext` reused for two concepts.

**Decision:**
- Capability flags: prefix with `supports_`. Canonical names: `supports_mid_turn_injection`, `supports_tool_approval_gating`, `supports_session_persistence`, `supports_session_resume`, `supports_session_fork`. Wire and backend match.
- Session naming: `SessionContext` = the **backend** object that bundles agent profile + skills + system prompt + tool defs + working dir. `SessionState` = the runtime state machine (started/idle/turn-active/cancelled/ended). `SessionInfo` = the wire payload sent to the frontend on `SESSION_HELLO`. Three distinct names, no overlap.
- Tool call IDs: `tool_call_id` everywhere (snake_case in JSON, `toolCallId` in TS).
- Turn IDs: `turn_id` everywhere. The legacy `runId` is renamed to `turn_id`.
- Display result kind field: `result_kind`, not `result_type` or `resultType`.

## D13 — Defer mid-turn injection to V1 in V0 build, but keep the abstract command in `HarnessSender` from day one

**Date:** 2026-04-08  
**Trigger:** Q2 from requirements + capability honesty (D3).

**Decision (recommendation to user — see synthesis report):** V0 does NOT implement mid-turn injection. `HarnessSender.inject_user_message()` exists in the abstraction (so OpenCode V1 can light it up trivially), but the V0 ClaudeCodeAdapter implementation raises `CapabilityNotSupported`. The capability flag is `False`. The frontend hides the affordance.

This is the orchestrator's **recommendation**; the user must confirm via Q2 in the synthesis report.

## D14 — Defer permission gating to V1; V0 runs with `bypassPermissions`

**Date:** 2026-04-08  
**Trigger:** Feasibility review medium #5 (approval policy mismatch in docs), Q2.

**Decision (recommendation):** V0 does NOT implement tool approval gating. The agent runs with `bypassPermissions` in Claude Code. `agent-loading.md` example profile is updated from `approval: confirm` to `approval: bypass` with a comment that V1 will add gating. Capability flag `supports_tool_approval_gating` is `False`. Frontend hides approve/deny buttons.

Recommendation; user confirms via Q2.

## D15 — Defer session persistence to V1; V0 is single-process, drop-on-restart

**Date:** 2026-04-08  
**Trigger:** Q2, alignment BLOCKER-3, capability honesty (D3).

**Decision (recommendation):** V0 has no session persistence. Restart = clean slate. `supports_session_persistence` = False. Files in the work item dir survive (that's the whole point of files-as-authority), but live conversation state does not.

Recommendation; user confirms via Q2.

## D16 — Decline to ship a no-terminal launcher in V0; document a one-line `meridian shell start` for someone-helping-Dad

**Date:** 2026-04-08  
**Trigger:** Alignment BLOCKER-4. Reviewer is correct that `meridian shell start` is terminal-first, which technically violates the customer reminder.

**Decision:** Acknowledge the gap. V0 ships `meridian shell start --work-item biomedical-yao` as the launch command. The "customer reminder" about Dad not touching a terminal is satisfied by **the developer (Jim) being the one who runs the install + launch on Dad's machine, then bookmarks the resulting localhost URL in Dad's browser**. This is acceptable for the validation phase because the user is hands-on with Dad. A real installer/launcher is V1.

The synthesis report flags this honestly: V0 is "Dad-friendly to use, developer-mediated to install." If the user disagrees and wants a launcher in V0, that's a scope addition the orchestrator surfaces.

## D17 — Don't ship Pydantic↔TypeScript codegen in V0; hand-maintained types

**Date:** 2026-04-08  
**Trigger:** Alignment MAJOR-2 — frontend-protocol.md proposes codegen + CI gating, which is V0 over-engineering for the load-bearing parts.

**Decision:** V0 maintains TS types in `frontend/src/lib/wire-types.ts` and Python types in `src/meridian/shell/schemas/wire.py` by hand. Both reference the canonical event schema in `harness-abstraction.md`. A test in the backend asserts the field names match. Codegen is V1 if drift becomes a real problem.

## D18 — Ship pre-built `frontend/dist` with releases; pnpm only required for development

**Date:** 2026-04-08  
**Trigger:** Alignment MAJOR-1, refactor review (pnpm/dist mismatch).

**Decision:** Releases (and the developer's local install on Dad's machine) ship `frontend/dist/` pre-built. `meridian shell start` serves the static bundle. `pnpm` is only required if you're doing frontend dev (`meridian shell dev`). `repository-layout.md` and `frontend-integration.md` are updated to match.

## D19 — Cut full Yjs collab editor; keep CM6 + content/formatting/paste/export, skip collab/persistence/transport/session

**Date:** 2026-04-08  
**Trigger:** Refactor review (editor scope), feasibility review (cut full editor), Q4.

**Decision:** Frontend `editor/` keeps:
- `editor/components/` — the editable surface
- `editor/content/`, `editor/formatting/`, `editor/paste/`, `editor/export/`
- `editor/title-header/`
- `editor/decorations/`, `editor/interaction/`

Cuts:
- `editor/collab/` — Yjs collab
- `editor/persistence/` — Yjs IndexedDB
- `editor/transport/` — Yjs transport
- `editor/session/` — Yjs session
- `editor/stories/` — keep in dev only, not in dist

Replace persistence with a simple `localStorage` autosave keyed on work item id. The editor renders a single markdown document that Dad uses for the results-section draft.

## D20 — Path-A vs Path-B mode is the responsibility of the agent + skill, not the shell

**Date:** 2026-04-08  
**Trigger:** Decision 10 in requirements + interactive tool framing.

**Decision:** The shell does NOT have a "Path A mode" or "Path B mode" toggle. The agent's data-analyst skill instructs it: "For each landmark detection, render the mesh, inspect your own output via vision; if confidence is low or unclear, call `pick_points_on_mesh`." This is a prompt-level decision, not a shell-level state. Keeps the shell domain-neutral (Decision 6).

The agent profile is updated to explicitly include this Path A/Path B fallback instruction.

## Findings deferred (not actioned in this design phase)

- **Feasibility critical-path risk #1 (jupyter_client + VTK stability over long sessions)**: not a design issue, an implementation/validation risk. Implementation phase will smoke-test with a 30-minute session early.
- **Feasibility critical-path risk #5 (biomedical skill corpus underspecified)**: agent-loading.md will be updated to include a richer placeholder for the biomedical-analyst skill but the actual skill content is implementation work, not design work. Flag in synthesis report.
- **Time-to-first-demo estimate**: not actionable in design; surface to user in synthesis report.

## Convergence pass changelog

- `design/harness-abstraction.md` — made the normalized schema canonical, added `submit_tool_result`, renamed capability flags to `supports_*`, moved the shell adapter home to `src/meridian/shell/`, and aligned Claude/OpenCode capability semantics with V0/V1 reality.
- `design/event-flow.md` — rewired the runtime narrative around `TurnOrchestrator` + `ToolExecutionCoordinator`, switched the flow to `turn_id` / `resultKind`, moved tool resumption to `submit_tool_result`, and simplified reconnect/session behavior to the single-process V0 model with `SESSION_RESYNC`.
- `design/frontend-protocol.md` — aligned `SESSION_HELLO` with effective V0 capabilities, added `SESSION_RESYNC`, updated tool/display wire shapes, documented simple multipart dataset ingest for V0, and replaced codegen with hand-maintained V0 wire types plus parity testing.
- `design/agent-loading.md` — moved `SessionContext` to `src/meridian/shell/session.py`, converged Claude init on `--append-system-prompt` + `--mcp-config`, changed the sample profile to `approval: bypass`, and added explicit Path A/Path B fallback guidance to the data-analyst prompt.
- `design/interactive-tool-protocol.md` — reinforced subprocess execution as the V0 model, made file handoff via `.meridian/interactive_inputs/<tool_call_id>/` explicit, renamed result envelopes to `tool_call_id`, and stated that Path A/B selection belongs in the agent prompt rather than shell state.
- `design/local-execution.md` — rewrote the runtime venv story around `~/.meridian/venvs/biomedical/` + `runtime/manifests/biomedical.toml`, removed the in-kernel interactive-tool recommendation in favor of subprocess coordination, and aligned session lifetime with the 30-second reconnect window.
- `design/repository-layout.md` — updated the shell tree to `session.py`, `adapters/`, `translator.py`, `router.py`, `turn.py`, `tools/coordinator.py`, and `runtime/manifests/`, removed biomedical heavy deps from `pyproject` extras in favor of `meridian shell init biomedical`, and switched the frontend/runtime story to ship prebuilt `frontend/dist`.
- `design/frontend-integration.md` — updated the frontend API/client story to simple dataset ingest and hand-maintained wire types, kept the CM6 drafting surface while explicitly cutting Yjs collab/persistence/transport/session paths, and aligned multi-tab/build behavior with the shared-session V0 model and prebuilt `frontend/dist`.
- `design/overview.md` — refreshed the component map to include `TurnOrchestrator` and `ToolExecutionCoordinator`, moved the biomedical runtime venv out of the project env, promoted Path A into V0, simplified V0 session scope to one process per work item, and documented the honest V0 launcher gap as developer-mediated.

## D21 — agent-shell-mvp replaces meridian-flow as the first MVP ("do things that don't scale")

**Date:** 2026-04-08
**Trigger:** Q1 resolution from dev-orchestrator session c1046.

**Decision:** agent-shell-mvp is the first MVP. meridian-flow (hosted Go/React biomedical platform) is paused until the agent-shell validation phase answers the product-direction question. Users bring their own Claude Code subscription, run the shell locally, and we host nothing. Infra cost for the first 100–1000 users is effectively zero. Once the validation phase reveals which direction is worth pursuing (biomedical life sciences, dev tooling + collaboration, creative writing orchestration, or something else), meridian-flow restarts with the generic harness designed around the validated use case — not the other way around.

**Why:** YC "do things that don't scale." The hosted platform is a bet on a specific vertical. Shipping a local BYO-harness shell decouples validation from infra spend and lets the first cohort of real users reveal which vertical is actually defensible. Designing the generic harness before knowing the target use case is premature abstraction at the business-model level.

**Implications for other open questions:**

- **Install burden** — no longer an "acceptable?" question. `uv tool install meridian-channel` + `uv sync` in the user's project is the *only* onboarding path, so onboarding UX is a first-class product concern, not a tradeoff.
- **D16 (no native launcher)** — stays accepted for V0. The first 100–1000 users are technical enough to run a CLI command. Polish the launcher after the product direction lands.
- **Q7 (unify meridian-channel spawn/session under HarnessAdapter in V1)** — still open but demoted in urgency. V0 ships without it; the unification move can happen once the shell has real users and we know whether architectural convergence is the right investment.
- **Domain-tool strategy** — reinforces the "meridian ships no domain tools" reframe. Users pick their own vertical via agent/skill/MCP packages pulled in through mars. The shell stays neutral; the *packages* carry the domain.
- **meridian-flow repo** — not deleted, not actively developed. Parked until the validation phase decides its target.

**Rejected alternative:** Coexist — keep pushing meridian-flow in parallel. Rejected because splitting effort across two products before the first has validated direction is how both fail to reach escape velocity. Focus beats coverage at pre-PMF scale.

## D22 — Agent/skill/MCP bundling via mars is the primary moat

**Date:** 2026-04-08
**Trigger:** Strategic observation during D21 discussion.

**Decision:** The defensible asset is not the shell (any team can wrap a harness in a UI) and not the harness abstraction (Claude/Codex/OpenCode will all stabilize their own surfaces over time). The moat is **mars as a package registry + resolver + materializer for composable agent capabilities** — agents, skills, and MCPs bundled as first-class units that a user can install into a neutral shell to get a working vertical.

The loop: more packages → more useful shell → more users → more package authors → more packages. Classic package-manager network effect, applied to agent augmentation instead of libraries.

**Why this matters for the roadmap:**

- **Shell stays neutral.** Every ounce of domain knowledge baked into the shell is a moat the shell doesn't get — because that knowledge should have been a package. The shell's job is to be the cleanest possible substrate for running packaged capabilities.
- **meridian ships no domain tools** (reinforced from D21). Verticals ship as packages, not as shell features.
- **mars-mcp-packaging is not a side feature.** It's foundational to the moat. The sooner mars can bundle agent + skill + MCP as a single installable unit, the sooner the biomedical validation doubles as a distribution dogfood — the Yao Lab "install" becomes `mars add biomedical-ucT-pack` rather than a bespoke setup.
- **Package discoverability + trust becomes a V1 priority.** Signing, provenance, a registry surface (even a plain-text index to start) — these are the moves that make the network effect kick in.
- **Validation metric shifts.** Success isn't "100 users running the shell"; it's "100 users running the shell AND N of them either authoring or installing third-party packages." The author-to-user ratio is the leading indicator of network-effect traction.

**Rejected framing:** "The shell is the product, packages are how we extend it." This is backwards — the *packages* are the product, the shell is the runtime. Investing heavily in shell features before mars can bundle capabilities is building the wrong asset.

**Implication for the correction pass:** the agent-shell-mvp design docs should stop treating mars as a setup-time detail and start treating it as the primary distribution story. The shell's value proposition to a new user is "install a package, get a working vertical" — which is only true if mars can do the bundling.

## D23 — The marketplace is the acquisition funnel for the eventual hosted platform

**Date:** 2026-04-08
**Trigger:** Strategic extension of D21 (park meridian-flow) + D22 (bundling is the moat).

**Decision:** The shell + mars marketplace is not just the V0 moat — it's the customer acquisition funnel for meridian-flow's eventual revival. Researchers (or dev-tooling authors, or creative-writing authors, depending on which vertical validates) who bundle and distribute their tools through mars are exactly the users who will move to a hosted cloud platform when they hit the limits of the local shell — collaboration, long-running compute, sharing results with colleagues who don't have the stack installed, persistent project state, multi-user sessions.

The migration path becomes: **(1)** author uses shell locally with their own Claude subscription, **(2)** bundles their workflow as a mars package, **(3)** distributes it to their lab/community, **(4)** the community hits collaboration/compute ceilings, **(5)** meridian-flow opens the upgrade path — same packages, same agents, same skills, same MCPs, but hosted. Because the package *is* the user's workflow, migration is frictionless — they don't have to port anything.

**Why this matters:**

- **Cold-start risk on the hosted platform drops to near-zero.** A vanilla cloud launch requires finding users from scratch; launching into an existing marketplace of researchers already using our shell means the hosted product ships to a captive audience on day one.
- **Package authors are the highest-LTV users.** They have workflows worth distributing, collaborators worth inviting, and pain points (collaboration, compute) that only a hosted platform solves. Optimize the shell + mars UX for authors first; consumers come along for free.
- **The validation question sharpens.** "Which vertical should meridian-flow target?" stops being guesswork. The vertical that gets the most mars packages, the most author-to-user ratio, and the most cross-user package installs **is** the vertical. The data tells us, the market doesn't need to be predicted.
- **Hosted platform design should assume marketplace continuity.** When meridian-flow restarts, the packages that already work locally must continue to work hosted — not a rewrite, not a re-listing, just the same mars manifest running against a different runtime. The harness abstraction and package contract need to survive the local → hosted transition. Design for it now even though we're not building it now.
- **Discoverability and trust infrastructure become more urgent, not less.** A marketplace that becomes a funnel needs provenance, signing, and basic moderation earlier than a marketplace that's "just" a moat. Push discoverability from "V1 priority" toward "V0.5 priority" — at least a plain-text index with install counts.

**Implication for the correction pass:** the agent-shell-mvp overview should explicitly name this three-act structure — V0 local shell, V0.5 marketplace surface, V1 hosted continuity — so the design work is framed around the funnel, not just the immediate MVP. The shell is not a destination; it's the top of the funnel.

**Cross-reference:** this decision changes the framing on Q7 (unify meridian-channel spawn/session under HarnessAdapter). Unification becomes more valuable, not less, because the same HarnessAdapter abstraction has to run both locally (shell) and hosted (flow). The unification move is how the local→hosted migration stays "same packages, different runtime" instead of "rewrite everything."

## D24 — Concierge package authoring for the first cohort

**Date:** 2026-04-08
**Trigger:** Tactical extension of D21 + D23.

**Decision:** For the first 5–10 customers (starting with Yao Lab), **we write the agent/skill/MCP packages with them**, not for them and not waiting for them to write their own. This is hands-on, high-touch, intentionally unscalable work — sit with the customer, watch their workflow, write the package, iterate, ship. Every concierge engagement produces a seed package for the marketplace, a case study, and a concrete signal about which parts of the workflow want to abstract into mars/shell infrastructure vs. stay custom to the customer.

**Why:**

- **Empty-marketplace problem.** A marketplace with zero packages can't be a moat or a funnel. We have to seed it. Writing the first packages ourselves is the fastest seeding path.
- **Customers won't author packages before seeing working ones.** The cold-start chicken/egg gets broken by us writing both sides of the first few interactions — the package and the user experience around it.
- **Package-format validation.** The agent/skill/MCP bundling contract is untested until real workflows hit it. Writing packages with customers under time pressure is the fastest way to discover where the format is wrong.
- **What should abstract vs. what shouldn't.** Every concierge engagement reveals patterns — three customers needing the same helper means that helper belongs in a reusable mars package; one-off needs stay custom. Without the concierge phase, we'd have to guess which abstractions earn their keep.
- **Highest-LTV relationships.** The customers we sit with become the first author-users — the ones who will bundle their own packages once they've seen how. These are the seed of the network effect.

**Staffing implication:** for the V0 validation phase, budget for humans (founders + maybe one hire) to spend real time inside customer workflows. This is not a product-led growth motion; it's founder-led concierge work. Accept the cost.

**Exit criterion:** concierge authoring ends when (a) at least 3 customers are successfully authoring packages without hand-holding, AND (b) the package-format changes per concierge engagement drop to near-zero. That's the signal the format has stabilized enough to support self-serve authoring, which is when V0.5 (marketplace surface) becomes worth investing in.

**Cross-reference:** this is how D23's funnel actually starts. Without concierge seeding, the marketplace sits empty and the funnel has no top. With it, the first 5–10 packages exist, the next 50 customers see working examples, and author-led growth can take over.

## D25 — Frontend is a generic chat UI with an MCP-driven renderer plugin surface

**Date:** 2026-04-08
**Trigger:** Extension of D22 (bundling as moat) + the "meridian ships no domain tools" reframe into the frontend layer.

**Decision:** The shell's frontend is **a generic chat UI** — no biomedical, no dev-tooling, no creative-writing domain code baked in. Domain-specific visualizations (3D mesh viewer, DICOM slice viewer, data table explorers, waveform viewers, whatever) are **frontend renderer plugins delivered through mars packages**, paired with the MCP server that produces their payloads.

**The contract:**

1. An MCP tool returns a structured payload with a `kind` discriminator: `{"kind": "mesh.3d", "data": {...mesh bytes...}}` or `{"kind": "dicom.slice", "data": {...}}`.
2. The shell backend forwards the payload verbatim to the frontend as a `ContentBlock` (canonical, harness-agnostic).
3. The frontend looks up the registered renderer for that `kind` and mounts the component with the payload.
4. The renderer component lives in the same mars package as the MCP server that emits the payload. Install the package → both halves land → the viewer "just works."

This means **mars packages grow a fourth artifact kind**: frontend renderer, alongside agent, skill, and MCP server. Same bundling model, different delivery target.

**Why:**

- **Reinforces the moat (D22).** The defensible asset isn't the shell or the frontend — it's the ecosystem of composable packages. Making the frontend neutral and renderer-extensible means package authors can ship entire user experiences, not just backend tools. Lock-in grows because leaving the shell means rebuilding every custom viewer.
- **Matches the D23 funnel.** A researcher who ships an interactive 3D bone-morphometry viewer through mars is building the hosted platform's killer feature for us for free, because the same renderer contract works locally and hosted (when meridian-flow revives).
- **Kills the `local-execution.md` biomedical venv assumption, properly.** Currently the design half-assumes the shell ships PyVista code. D25 plus the PyVista-as-MCP reframe means the shell ships *zero* biomedical code. The biomedical package ships a Python MCP server (PyVista computation) + a JS renderer (Three.js/R3F mesh viewer). Same package. Both halves via mars.
- **Frontend becomes commoditized but trustworthy.** The shell's own UI is small — message list, input box, attachment strip, content-block dispatcher. Everything domain-specific is a plugin. This is easy to audit, easy to theme, and easy for third parties to fork or replace.

**Hard questions this opens** (must be answered in the correction pass or deferred explicitly):

1. **Renderer delivery format.** Prebuilt ES modules loaded dynamically? WASM components? Web Components? iframe sandboxes? Each has different tradeoffs for trust, performance, and authoring ergonomics. V0 probably wants the simplest: prebuilt ESM bundles referenced by the mars package manifest, loaded dynamically by the shell's frontend.
2. **Trust boundary.** Loading arbitrary JS from a package is a real security concern, especially once the marketplace has third-party authors. Options: sandbox renderers in iframes with postMessage, restrict to a vetted set of primitives (charts, tables, meshes), or require package signing before load. Probably a combination. The V0 answer can be "only load renderers from packages the user explicitly installed" — good enough to ship, not good enough long-term.
3. **Renderer ↔ MCP kind registration.** How does the frontend know `mesh.3d` maps to `pyvista-viewer@1.2.0/MeshRenderer.js`? Almost certainly: mars package manifest declares `renderers: [{kind: "mesh.3d", entry: "frontend/mesh-renderer.js"}]`, mars sync emits a merged registry file under `.agents/frontend/registry.json`, shell frontend loads it at boot. Same materialization discipline as agents and skills.
4. **Shared renderer contracts.** Do we ship a set of standard `kind`s the frontend understands natively (`chart.line`, `table.data`, `image.png`, `text.markdown`) so packages don't all have to ship custom renderers for basic types? Yes — call these "core renderers," ship them with the shell, and custom renderers only appear when a package needs something bespoke.
5. **State and interactivity.** Some renderers are read-only (display a chart), some are interactive (rotate a mesh, step through DICOM slices, select a region). Interactive renderers may need to send events *back* to the agent — "user selected this region, run landmark detection here." This needs a frontend-to-MCP reverse channel, which doesn't exist yet and is a real new design surface. V0 can punt on reverse channels (read-only renderers only) but should not paint us into a corner.

**Cross-reference:** this decision makes the mars/meridian-channel separation argument (D21+D22+D23) even stronger. Mars is now distributing code that runs in three environments (agent prompt context, local Python subprocess, browser JS), which is pure ecosystem infrastructure. There is nothing about this that is specific to meridian-channel's CLI surface — it's a standalone product category.

**Implication for the correction pass:** this is the biggest change to the existing design docs. `interactive-tool-protocol.md` needs a near-total rewrite around the renderer-plugin model. `frontend-integration.md` and `repository-layout.md` need to stop treating the 3D viewer as shell-internal. `overview.md` needs the generic-chat-UI + renderer-plugin framing up front. `harness-abstraction.md` is mostly unaffected except where §9.5.1 currently describes PyVista as shell-internal — that section dies entirely.

## D26 — Extensions are (frontend + MCP) interaction-layer pairs with bidirectional event flow

**Date:** 2026-04-08
**Trigger:** Clarification of "extensions" during the mars/meridian-channel separation discussion. The user specifically named dedicated DICOM viewer, 2D image viewer, and 3D mesh viewer as examples — interactive surfaces where the user clicks, drags, or scrolls, and the agent/MCP reacts.

**Decision:** The primary extension model for the shell is the **interaction-layer package** — a mars package that ships a frontend component and an MCP server together, with a wiring manifest declaring they belong together. The word "renderer" from D25 is too passive; the extension is a **bidirectional interface between the user and the agent**, not a one-way display.

**The contract (tightens and extends D25):**

1. **Mars package declares a composite extension**: `{kind: "interaction-layer", frontend: "dist/viewer.js", mcp: {command: "python", args: [...]}, dispatch_kind: "dicom.stack"}`
2. **Initial payload path (existing D25)**: Agent calls MCP tool → MCP returns `{"kind": "dicom.stack", "data": {...}}` → backend forwards to frontend as a ContentBlock → frontend mounts the registered component.
3. **Reverse event path (new)**: The mounted frontend component can emit events back: `{"kind": "dicom.roi_selected", "slice": 47, "bbox": [...], "target_mcp": "dicom-viewer@1.0"}`. These events flow to the paired MCP server (either directly or via a shell-backend relay — see open question below).
4. **The agent can observe or not.** Some extension events want to go into the agent's context (e.g., "user selected this region, run segmentation here"); others are purely user-to-extension with no agent visibility (e.g., "user scrolled from slice 47 to 48"). The wiring manifest or the event itself decides.
5. **Packages compose.** A biomedical vertical might ship a single package bundling a DICOM viewer, a 3D mesh viewer, a segmentation MCP, and a morphometrics agent — all installable with one `mars add biomedical-ucT-pack`.

**Why this matters:**

- **Reverses D25's hard question #5 (reverse channels).** It's not deferrable. Without reverse flow, extensions are slideshows, and slideshows don't validate segmentation or drive landmark detection. The entire Yao Lab validation scenario depends on interactive viewers.
- **Confirms the trust split from the mars-separation discussion.** Extensions run in browser sandbox (frontend) + subprocess MCP (backend). Neither touches meridian-channel's process. Mars can ship extensions freely; the trust boundary only bites when mars tries to ship in-process code like CLI commands or harness adapters, and we've already said it doesn't.
- **Clarifies what the frontend "extensibility" question from D25 actually is.** V0 extensibility = interaction-layer plugins with bidirectional events. V1 = broader surface (sidebars, commands, routes) if needed. The V0 target is narrower and more concrete than the (b)/(c)/(d) spectrum I proposed — it's not about how much of the chrome plugins can modify, it's about whether plugins are interactive *within* the content area.
- **Makes the correction pass concrete.** `interactive-tool-protocol.md` needs to be rebuilt around this contract specifically. The V0 examples the doc should use are: DICOM viewer, 2D image viewer, 3D mesh viewer. Not "a generic renderer plugin" — those three concrete cases.

**Open architectural question (V0 blocker):**

**Does the frontend extension talk to its paired MCP directly, or through a shell-backend relay?**

- **Direct**: Frontend opens a channel straight to the MCP subprocess. Simpler for the extension author, one fewer hop, lowest latency. But it means exposing the MCP protocol to browser code and losing the shell's ability to audit, rate-limit, authenticate, or intercept. If the extension is local-only this is probably fine; once meridian-flow revives as hosted, it's a cross-tenant security hole.
- **Relay**: Frontend sends events to the shell backend, shell routes to the MCP. One extra hop, but the shell stays in the middle — can log, audit, enforce policy, and make the local → hosted migration trivial because the frontend never knew where the MCP was running. The cost is defining yet another wire protocol (frontend ↔ backend extension events) and making sure it's extensible.

**Recommendation:** **Relay**, and treat the relay protocol as a published contract from V0. This matches D23's "same packages, different runtime" migration story — a hosted meridian-flow uses the same frontend, the same extension packages, and the same relay protocol, with only the backend origin changing. Direct-MCP would bake local assumptions into the extension author's mental model and break the funnel.

The cost is one more design doc in the correction pass: `extension-relay-protocol.md` or a new section inside `frontend-protocol.md`.

**Implication for the mars-mcp-packaging work item:** the package schema must support declaring composite extensions, not just MCP servers standalone. The receiving dev-orchestrator needs to know this before designing the schema, otherwise they'll design a schema that handles MCPs cleanly but can't express the MCP-plus-frontend pairing.

## D27 — CLI plugins and harness adapters deferred, not architecturally rejected

**Date:** 2026-04-08
**Trigger:** User clarification immediately after D26 — CLI plugins are eventually in scope, just not V0/V1 priority.

**Decision:** The trust split from the mars-separation discussion (mars ships data + sandboxed code; meridian-channel core ships in-process code) is a **V0/V1 posture, not a permanent architectural boundary**. Eventually, mars may ship items that execute inside meridian-channel's process — CLI subcommands, custom harness adapters, routing hooks — but only after the trust infrastructure exists to support it safely: package signing, provenance, revocation, explicit user opt-in per-package, and a clear sandbox story for in-process Python code (subinterpreters, capability restrictions, or similar).

**V0/V1 scope stays narrow:**

- Mars ships: agent, skill, MCP server, interaction-layer extension (frontend + MCP pair), workflow templates (V1).
- Mars does **not** ship: CLI commands, harness adapters, routing hooks, anything that runs inside meridian-channel's Python process.

**V2+ door stays open:**

- The mars item schema should be extensible enough to add new `ItemKind`s without migration. `ItemKind::CliCommand` or `ItemKind::HarnessAdapter` should be a mechanical addition when the time comes.
- Don't design the current item kinds in a way that assumes in-process items will never exist. No hardcoded list in a place that would need rewriting; enum extensibility and dispatch tables instead.

**Practical effect on the correction pass and mars-mcp-packaging:** no change in scope. V0 ships what D25/D26 describe. This decision exists only to prevent future-me from reading the trust split as "mars is forever a sandbox-only system" and then architecting the schema in a way that makes extending it painful.

## D28 — Architecture wide, implementation narrow: "think big from extensibility, keep MVP focused but extensible"

**Date:** 2026-04-08
**Trigger:** Direct framing from the user after accumulating D21–D27. Serves as the governing principle for all preceding decisions and the correction pass.

**Decision:** The architecture should anticipate a wide extension surface and ship stable, published contracts at every seam from V0 onward. The implementation should be **ruthlessly narrow** — the smallest code footprint that (a) validates Yao Lab end-to-end, (b) proves the moat bet (D22/D23), and (c) does not trap us in six months. Extension points are first-class in V0 even when most of them are stubs; stubs are cheap, painful retrofits are not.

**The two tests every V0 choice must pass:**

1. **"Does removing this block Yao Lab validation?"** — If no, cut the feature. This is the focus test.
2. **"If we succeed, does this choice trap us in six months?"** — If yes, redesign. This is the extensibility test.

Most V0 choices pass one test and fail the other. The interesting work is the choices that pass both.

**What "architecture wide" means concretely (against D21–D27):**

- **Mars `ItemKind` is an open/extensible enum.** V0 ships 4 kinds (agent, skill, MCP server, interaction-layer extension); V1 adds workflow templates; V2+ can add CLI commands and harness adapters per D27 once trust infrastructure exists. Adding a kind should be mechanical — no schema migration, no fork in materialization logic.
- **Every seam is a published versioned contract from V0.** The wire protocols that matter:
  - Normalized event schema (harness ↔ shell backend)
  - Content block wire format (shell backend ↔ frontend)
  - Interaction-layer relay protocol (frontend ↔ paired MCP via shell relay, per D26)
  - Mars package manifest schema (package author ↔ mars)
  - Shell ↔ mars install/sync contract (shell ↔ mars CLI)
  Each gets a `VERSION` field and a compatibility discipline (additive-only in V0; semver after).
- **Mars is architected as standalone from the start** (per the mars-separation direction the user confirmed). Meridian-channel is one consumer of mars, not its owner. Any API mars exposes is designed as if an unrelated third party might call it — because eventually one will.
- **Frontend is designed for extraction and replacement.** Wire protocol is the seam; frontend knows nothing privileged about the backend. Extraction into its own repo is deferred to "when protocol stabilizes," but the design treats the frontend as if it were already extracted — no cross-boundary imports, no shared in-process state, no undocumented assumptions.
- **Extension schema allows composite extensions** (interaction-layer pairs per D26) even though V0 only ships one real example (PyVista 3D mesh viewer, shipped externally as a mars package, not bundled in the shell).

**What "implementation narrow" means concretely (against D21–D27):**

- **V0 mars ships:** 4 `ItemKind`s. Agent and skill already work; MCP server and interaction-layer extension are new. No marketplace UI — discovery via direct manifest URLs. No signing infrastructure — reserved as a schema hook, no-op in V0. No dependency solver — delegate to `uv` for Python MCPs.
- **V0 shell ships:** minimum chat UI chrome (message list, input box, attachment strip), content-block dispatcher, 3–5 core renderers (text/markdown, image, table, simple chart), and the relay layer for interaction-layer extensions. **Zero biomedical code.** The PyVista viewer is an externally-installed mars package, not a shell feature.
- **V0 wire protocols:** all published, all versioned, all additive-only. One working example per seam. No multi-version negotiation in V0 — "both sides must be the same version" is fine for a local shell.
- **V0 does not ship:** auth, billing, hosted flow, multi-tenant anything, marketplace search/listing UI, package signing enforcement, extension relay protocols beyond what Yao Lab needs, CLI plugin loader, harness adapter loader, workflow template engine. These are all documented as extension points with schema hooks but no implementation.
- **V0 concierge scope (per D24):** we write the Yao Lab package by hand. That package exercises every extension point that V0 claims to support. If Yao Lab's package hits a wall, that's a V0 bug; if it doesn't, V0 is done.

**What this means for the remaining open items from earlier in the session:**

- **Frontend as own repo**: *architecture wide says yes, implementation narrow says not yet*. Design for extraction, wire protocol is published, but the repo doesn't get extracted in V0. Extraction happens when someone else wants to consume it — which will tell us the protocol is actually stable.
- **Mars/meridian-channel separation**: *architecture wide says done, implementation narrow says leave the current `meridian mars sync` CLI coupling alone for now*. Mars already ships as its own binary from a separate repo; the strategic framing is "mars is a standalone product," but we don't rename `meridian mars` commands or spin up a separate mars.sh site in V0. Those are D23-V0.5 moves once the marketplace surface becomes real.
- **Extension relay protocol details**: *architecture wide says published from V0, implementation narrow says design the envelope + ship one working example*. The envelope needs: event id, kind, payload, direction, timestamp, target extension id. The one working example is PyVista's 3D mesh viewer interaction events. Everything else is schema hooks.

**This decision governs the correction pass.** Any correction pass finding that reads as "we should also ship X" must pass both tests before it lands in the design docs. Most "shoulds" will fail the focus test and get cut. The ones that pass become extension points with stubs; the ones that pass *and* are in Yao Lab's path become V0 features.

**Net effect on accumulated strategy:** D21–D27 are not scope expansion — they are the scaffolding that makes a narrow V0 non-trapping. Without them, a narrow V0 is a tech debt generator. With them, a narrow V0 is a clean foundation that grows by addition, not by rewrite. This is the whole "do things that don't scale" bet: the thing we ship is small, but the thing we architect around is the full funnel (D23) and the full moat (D22).

## D29 — Implementation SRP/SOLID must mirror the strategic boundaries from D21–D28

**Date:** 2026-04-08
**Trigger:** User reminder that the accumulated strategic decisions should inform implementation structure, not just design docs.

**Decision:** The code organization for agent-shell-mvp (and any follow-on work in meridian-channel, mars, or the eventual frontend extraction) must mirror the strategic boundaries from D21–D28 one-to-one. SRP and SOLID here are not abstract good-practice rhetoric — they are the mechanism by which the D22 moat and D23 funnel stay achievable. If the code couples things that the strategy says are independent, the strategy dies on the first real refactor.

**The boundaries that must be enforced in the code:**

1. **mars ↔ meridian-channel**: already two repos, two binaries. Enforce: meridian-channel depends on `mars` via process invocation only, never by importing mars internals. Mars releases ship independently. Any shared types live in a published contract (JSON schema, protobuf, or mars CLI output format), not a shared library. If you find yourself wanting to `from mars import ...` from meridian-channel, stop and design the contract instead.
2. **meridian-channel (coordination) ↔ agent-shell (backend process)**: the shell is a subcommand of meridian-channel today, but conceptually it is a distinct consumer of the harness abstraction. Under `src/meridian/shell/` the code must not reach up into `src/meridian/lib/` for anything beyond the documented harness adapter interface. If the shell needs something from the coordination layer that isn't in the interface, add it to the interface — don't import a helper.
3. **Shell backend ↔ frontend**: the wire protocol (normalized events, content blocks, interaction-layer relay) is the only coupling. Backend code must not assume frontend shape; frontend code must not assume backend process internals. This is the D28 "design for extraction" rule made concrete: if the frontend moves to its own repo tomorrow, the backend shouldn't notice.
4. **Shell ↔ extensions**: a mars extension package is a trust boundary. The shell loads the manifest, materializes the artifacts, spawns the MCP subprocess, and relays events. The shell must not import extension code, must not assume extension internal state, and must not trust extension input without validation. Treat every extension as hostile code that happens to be installed — not because we distrust authors, but because the pattern is the only way the V2 CLI-plugin future stays safe.
5. **Harness adapters as the ONLY integration surface per harness**: each adapter (Claude, Codex, OpenCode) lives in its own module with its own tests. Shared utility code goes into a base class or a helpers module that every adapter can depend on, but adapter modules may not import each other. Adding a new harness = new adapter file + registration. Modifying Claude behavior must not touch Codex or OpenCode code.

**Structural rules that follow:**

- **One responsibility per module**, where "responsibility" is defined by the strategic boundary, not by code size. A 2000-line module that implements one coherent thing is fine; a 200-line module that reaches across three boundaries is not.
- **Interfaces before implementations**: every boundary gets a Protocol / ABC / TypedDict published before the code behind it exists. This is how D28's "published wire contracts from V0" manifests in the Python code.
- **Dependency direction is downhill**: high-level strategy modules (shell, router, turn orchestrator) depend on low-level capability modules (harness adapter, tool coordinator, relay), never the reverse. If a low-level module needs to know what the high level is doing, the dependency is inverted (callback, event stream, or protocol).
- **Test boundaries match module boundaries**: each boundary gets smoke-testable from the outside. If a boundary can't be smoke-tested without reaching into internals, the boundary is wrong.
- **Refactor continuously, not in batches**: per dev-principles, run @refactor-reviewer during design review and again in the final implementation review loop. Structural findings are not deferred to "cleanup passes." The same D28 posture ("architecture wide, implementation narrow") applies to code maintenance — the narrow V0 implementation stays narrow by continuous refactoring, not by accumulating debt and then triaging.

**Implication for the planner phase:**

When the design correction converges and the planner decomposes the design into implementation phases, the phase boundaries should line up with the code boundaries above. One phase per subsystem, one smoke-testable seam at the end of each phase. If a phase crosses a boundary, split it. If two phases couple to the same seam, merge them.

The planner should explicitly enumerate the phase-to-boundary mapping before decomposing work, and the phase staffing should include @refactor-reviewer passes at every phase gate, not just the final loop.

**Implication for review staffing:**

Reviews of the correction pass and the subsequent implementation phases should include @refactor-reviewer with specific focus on boundary integrity:

- Does any new code cross a boundary from D29?
- Does any new interface leak implementation detail from one side to the other?
- Does any module take a dependency that flows uphill instead of downhill?
- Does the test suite actually exercise the boundaries, or does it reach through them?

These are not code-style nits. They are the mechanism that keeps the strategic bet alive through six months of implementation churn.

## D30 — Ship capabilities at the highest useful granularity

**Date:** 2026-04-08
**Trigger:** User observation that MCP is mostly a useless abstraction compared to a well-designed CLI for developer work, and that playwright (the one MCP the user finds useful) is verbose and sprawls too many small tools that don't matter.

**Decision:** Capability packaging follows one rule: **ship at the highest useful granularity**. A CLI binary with good flags is strictly better than an SDK method is strictly better than an MCP with a bag of small methods, and an MCP with one rich operation is strictly better than an MCP with 25 micro-operations. Every tool in the agent's system prompt must earn its context budget; tool-surface sprawl is a design smell, not a feature.

**The ranking (highest to lowest preference for the developer track):**

1. **Pre-existing CLI** — `pytest`, `ruff`, `uv`, `git`, `gh`, `jq`, `rg`, `curl`. Already composable, already inspectable, already in the agent's training data. The agent uses them through the harness's existing Bash tool. Cost: zero context budget beyond what the skill teaches.
2. **New CLI you write** — a small Python/Bash script shipped via the pack. Still composable, still inspectable. Cost: description of what it does lives in the skill, not in the system prompt.
3. **One rich MCP operation** — a single tool like `browser_run_code(snippet)` that accepts a rich argument. Cost: one entry in the tool list, one description, accepts arbitrary composition through its argument.
4. **Multiple MCP operations** — only when the interaction genuinely requires distinct surfaces that can't compose through a single argument. Rare. Cost: N entries in the tool list, N descriptions, the agent has to reason about which applies.
5. **Verbose MCP with 25 micro-operations** — playwright-as-currently-shipped shape. **Avoid unless there's an overriding reason.** Cost: massive system prompt bloat, the agent has to reason about vocabulary it didn't learn in training, composition happens across multiple tool calls instead of within one, every turn pays the context tax.

**The reason tool-surface sprawl is a smell:** every tool entry costs context budget *every turn*, not just when it's used. A 25-tool MCP eats on the order of 2–5k tokens of system prompt for capabilities that a single rich tool could express in 200. Over a long session that's tens of thousands of tokens of pure overhead. The agent also has to reason about which verb to use — adding cognitive load that would disappear if the tool were a CLI the model already knows how to invoke.

**Why small CLIs win over clever MCPs:** the model has already seen `pytest`, `git`, `rg`, `curl`, `ffmpeg`, `pandoc`, and thousands of other CLIs in its training data. It knows their flags. It knows their idioms. It knows the error messages. Every time we wrap a CLI in an MCP, we're throwing away that training-time knowledge and forcing the model to learn a custom vocabulary at inference time. The MCP is strictly worse.

**When MCP is the right answer** (the carve-out):

- **Genuinely stateful bidirectional interaction** — the state is too complex to serialize across calls, and the interaction must persist across multiple turns. The canonical case is the researcher-track interaction-layer extensions from D26 (DICOM viewer, 3D mesh segmentation editor, statistics explorer). The user clicks, the model sees, the model responds, the view updates. This cannot be a CLI.
- **Native access to a runtime the CLI can't reach** — a running Jupyter kernel with live variables, a debugger sitting on a breakpoint, a database connection with an open transaction. The state belongs to a process the CLI would have to relaunch.
- **Structured observations the model needs to reason about at high fidelity** — a DOM tree where text output loses structure, a 3D mesh where vertex arrays matter. The MCP can return the structure; a CLI would have to serialize it badly.

Even in these cases, **ship the fewest, richest operations that cover the interaction model.** Not the largest enumeration of possible actions.

**Enforcement mechanism (for now, not code):** concierge authoring reviews. When we write the first reference packs with customers, every MCP that surfaces goes through a "could this be a CLI?" gate and a "can these N operations collapse into one rich one?" gate. Both gates are judgment calls; neither belongs in a schema validator. Publish the guidance in the `mars-capability-packaging` design docs as a checklist package authors walk through, not as a schema constraint the tool enforces.

**Implication for the first developer-track reference pack** (the TDD pack or whichever we pick first):

```
tdd-pack/
├── agents/
│   └── tdd-practitioner.md       # persona + methodology
├── skills/
│   ├── red-green-refactor.md     # when to write tests, when to refactor
│   └── pytest-usage.md           # canonical invocations, flag idioms
├── cli-deps/
│   └── manifest.toml             # pytest>=7, coverage>=7
└── mars.toml
```

**Zero MCPs, zero wrapper scripts, zero custom tools.** The agent invokes `pytest` and `coverage` directly through the harness's Bash tool. The skill teaches the invocation patterns. The pack earns its context budget through methodology, not tool surface.

If this pack is worse than an MCP-based equivalent, the CLI-first hypothesis is wrong and we should know immediately. If it's better (the expectation), it becomes the template for every subsequent developer-track reference pack.

**Implication for the mars work item:** the work item currently named `mars-mcp-packaging` is misframed. The primary V0 new capability kind is **CLI-deps** (agent + skill + "install these CLIs via uv/npm/cargo"), not MCP. MCP support remains necessary for the researcher track (D26 interaction-layer extensions) and the rare developer-track stateful cases, but it is the *second* priority, not the first. Renamed and rescoped in parallel with this decision.

**Implication for D22 (bundling as moat):** the moat is still bundling, but the primitives being bundled shift. A mars pack bundles: agents (how to behave), skills (what methodology to apply), CLI-deps (what tools to have available), and — when genuinely stateful — MCPs with minimal rich operations. The pack, not the MCP, is the unit of distribution and the unit of the moat.

**Implication for D28 (architecture wide, implementation narrow):** V0 implementation narrows further. MCP bundling machinery still gets designed and stubbed (architecture wide), but the first *working* mars capability kind shipped beyond agent+skill is CLI-deps (implementation narrow). MCP support follows when the first stateful case — probably from the researcher track — forces it.

## D31 — Project-scoped capability loading, never global

**Date:** 2026-04-08
**Trigger:** User observation that MCPs are useful per-project but terrible when installed system-wide — and the broader complaint that Claude Code's native plugin/MCP system installs capabilities globally, so every project pays the context tax for every capability ever added.

**Decision:** Every capability installed through mars is **project-scoped and never global**. A mars pack installed into project A is visible only in project A. No `~/.config/mars/`, no `~/.mcp/`, no `/usr/local/share/agents/`, no cross-project bleed-through. The project's own directory tree is the only install target. This mirrors the convention of every sane package manager of the last twenty years (npm, uv, cargo, gem) and inverts Claude Code's current system-wide plugin model.

**The rule applied across all capability kinds:**

| Kind | Location | Already true? |
|---|---|---|
| Agent | `.agents/agents/` | ✓ |
| Skill | `.agents/skills/` | ✓ |
| CLI-dep (D30) | project's `pyproject.toml` / `package.json` / `Cargo.toml` | ✓ (naturally, via uv/npm/cargo) |
| MCP server | `.agents/mcp/` with per-harness config pointers, loaded at spawn time via `--mcp-config` or equivalent | needs design |
| Frontend extension (researcher track) | `.agents/extensions/` with manifest, loaded by the shell when it starts in that project | needs design |
| Workflow template (V1) | `.agents/workflows/` | future |
| CLI plugin (V2+, D27) | reserved — when it arrives, also project-scoped | future |

**Why this matters:**

- **Context budget isolation.** A refactoring project doesn't load DICOM viewer tools. A biomedical project doesn't load web-scraping MCPs. Each project's agent prompt carries only the capabilities it actually uses, which matters directly because every loaded tool eats system-prompt tokens every turn (per D30).
- **Reproducibility.** `git clone && uv sync && mars sync` produces the same capability set as the author's project, because the project tree carries everything. Global state that lives outside the project can't be reproduced from the project itself.
- **Trust and auditability.** A user can read their project's `.agents/` and `pyproject.toml` and see every capability that was installed. No hidden state, no "this MCP is loaded because you installed it six months ago and forgot."
- **Team and CI portability.** A team member who checks out the project and runs `mars sync` gets the same tools. A CI runner gets the same tools. No "works on my machine because of my global config."
- **Matches D28's "project is a normal Python project" constraint** one-to-one. A normal Python project has its own venv, its own pyproject, its own state. Mars slotting capabilities into that scope is the natural extension; mars writing outside it would break the constraint.

**The real problem this exposes** (and the planner / mars-capability-packaging work item must address):

Claude Code's `--mcp-config` flag *adds* MCPs to the session; it does not *replace* whatever Claude Code has loaded from its user-level global config. So even if mars installs everything project-scoped, the user's pre-existing global MCPs still bleed into every meridian-channel-launched Claude Code spawn. Three realistic options, none of them clean:

1. **Document and recommend**: "Disable your global Claude Code MCPs when using meridian-channel." Simplest, worst UX.
2. **Config-directory isolation**: launch the harness with a custom `$XDG_CONFIG_HOME` or `$HOME` pointing at a project-scoped shim directory that excludes global config. Requires per-harness adapter knowledge. Probably the right long-term answer.
3. **Accept the bleed** for V0: global MCPs continue to load, mars adds project-scoped ones on top. Violates the scoping rule but requires zero workaround. Reasonable V0 compromise.

**Recommended approach:** V0 ships with (3) — accept the bleed, document the limitation, acknowledge we're violating our own rule because the workaround isn't worth the V0 complexity. V0.5 or V1 implements (2) once we know which harness adapters need which isolation mechanism. Codex's `thread/start` config and OpenCode's session API may support native "ignore globals" semantics — the planner should check per harness before committing to a strategy.

**Implication for the harness adapters design**: each adapter must own its own strategy for scoping capability loading. Claude Code adapter passes `--mcp-config`. Codex adapter uses `thread/start` config. OpenCode adapter uses session config. The `HarnessAdapter` interface exposes `load_capabilities(project_scope)` (or equivalent) as a mandatory method; how the adapter achieves project-scoping is its internal detail, but the *semantics* — "this spawn sees only these capabilities" — is the published contract.

**Implication for `mars-capability-packaging`**: the V0 design must explicitly state that mars writes nowhere outside the project tree. Any draft that proposes a `~/.mars/` cache or global registry is wrong. The work item's requirements already carry "project is a normal Python project" from D28; this decision extends that to "project is also the only scope for capability visibility."

**Implication for the `agent-shell-mvp` correction pass output**: the correction pass did not know about D31 (landed after the spawn). The new `design/execution/project-layout.md`, `design/extensions/package-contract.md`, and `design/harness/adapters.md` likely need a short addition stating the project-scoping rule explicitly. Small scope — worth folding into the follow-up short correction pass alongside D29/D30.

**Cross-reference:** this decision is load-bearing for the "do things that don't scale" framing in D21. A user trying out meridian-channel for the first time on a single project should not have to rearrange their global config, disable other tools, or worry that installing a mars pack will affect other projects. The BYO-subscription low-friction onboarding story depends on project isolation.

## D32 — Amends D31: scope is explicit, install is separate from activation

**Date:** 2026-04-08
**Trigger:** User correction to D31 — "system wide is sometimes good." D31 captured a real concern (surprise global state is bad) but overcorrected on the solution ("mars writes nowhere outside the project"). Legitimate use cases for user-scoped installs exist, and the right rule is not "never global" but **"scope is explicit and install is separate from activation."**

**Decision:** Mars supports multiple install scopes (project, user, system) and treats them as first-class concepts. The principle that drives good behavior is not "always project-scoped" but **"install location is separate from activation, and both are explicit."** A pack installed at user scope does not automatically become active in every project; the project opts in.

This supersedes D31's absolutism while preserving its real point (no surprise global state, context-budget isolation).

**The four-part rule:**

1. **Install scope is explicit.** When the user runs `mars add <pack>`, the default is project scope (`.agents/` in the project tree). The user can choose user scope with `mars install --user <pack>` (pack lives in `~/.config/mars/` or XDG equivalent) or system scope with `--system` (rare, V0 probably doesn't implement it). Mars never silently picks a scope the user didn't ask for.

2. **Activation is explicit and per-project.** A pack being installed at user scope does not automatically make it active in every project. The project must opt in — either through a per-project activation list in `.agents/` or by activating user packs at invocation time. **Context budget isolation comes from this rule, not from preventing user installs.** A project only loads the packs it opted into, so the token cost is bounded by what that project actually uses.

3. **Shadowing follows the standard pattern.** Project activations override user ones when names collide, user overrides system. Same mental model as git config (`--local > --global > --system`), shell PATH, Python sys.path. This lets a user run a patched `tdd-pack@2.1-local` in one project while keeping `tdd-pack@2.0` at user scope for every other project.

4. **Surprise-free rule (the real principle under D31).** Mars never writes to a scope the user didn't explicitly choose, and never activates a pack a project didn't explicitly opt into. A user who installs a pack at user scope does not discover later that it silently started affecting unrelated projects.

**Legitimate uses of user scope (the cases D31 was wrong about):**

- **Personal methodology skills**: a user's preferred code review style, commit message conventions, refactoring heuristics. Install once, activate in whichever projects want them.
- **Default agents**: the user's preferred @coder, @reviewer, @architect. Installed once, activated per-project by default or explicitly.
- **Cross-project domain packs**: a biomedical researcher with 10 μCT projects installs the biomedical pack once at user scope, activates in each project as needed. Re-installing per project is churn for no benefit.
- **Meta-tooling**: meridian-channel itself is installed via `uv tool install meridian-channel` — we already accept user-scope tools. Mars is consistent with that convention.

**The Claude Code bleed-through problem from D31 gets reframed:**

D31's worry was "user's pre-existing Claude Code global MCPs bleed into every project." Under D32, the reframe is: that's the user's Claude-Code-native global state, and it coexists with mars state. Mars doesn't try to erase or override it. If the user wants full isolation (no Claude-native globals visible to meridian-launched spawns), they can opt in to a harness-adapter-level isolation mode (custom `$XDG_CONFIG_HOME`, shim directory, etc.) — but that's a user choice, not a mars-enforced default.

This is strictly better for V0 UX than D31's implied workaround: it means a user can try meridian-channel without touching their existing Claude Code configuration, because mars and Claude-native globals just coexist by default.

**Implications for `mars-capability-packaging`:**

- **Scope is a first-class concept in the schema.** Each item kind declares a default scope appropriate to its nature (agents and skills default to user-friendly, CLI-deps and project-bound MCPs default to project), and install-time flags override.
- **Two separate materialization paths:** project-scope installs write to `.agents/` in the project tree. User-scope installs write to `~/.config/mars/` (or XDG). System-scope is reserved and probably not implemented in V0.
- **Activation is its own schema element.** A project's `.agents/activation.toml` (or equivalent) lists which user-scoped packs are active in that project. This is small, human-readable, and commits to git so the team shares the same activation state.
- **Shadowing logic** is mechanical — when merging capability lists, project entries win over user entries win over system entries. Implemented as a deterministic merge in mars, not scattered across loaders.

**Implications for the harness adapters:**

Each adapter loads capabilities from the merged view — project activations plus opted-in user activations, with conflict resolution by scope priority. Adapter doesn't care where an entry came from, only that it's in the final merged list. The merge happens in mars (or in a shared utility meridian-channel owns), not inside each adapter.

**Implications for the correction pass addendum already teed up:**

The follow-up correction pass now folds in D29 + D30 + D31 + D32 + dual-track framing. The net message to the design corpus about capability scoping is D32's four-part rule, not D31's "never global." The planner reads both D31 and D32 and takes the D32 version as the operative rule (D31 is preserved for history; D32 amends).

**What this does NOT change:**

- D30 (ship at highest useful granularity, CLI > verbose MCP) is untouched.
- D28 (project is a normal Python project) is untouched — project-scope is still the default and still the most common install target; D32 just acknowledges that user scope is also legitimate.
- The "no surprise global state" principle is kept; D32 sharpens it from "no global state" to "no state at a scope the user didn't ask for."

**Net effect:** D32 replaces D31's absolute rule with a scoped rule that covers more legitimate use cases while still delivering D31's intended outcome (context budget isolation, reproducibility, no surprise state). D31 stays in the log for history but its operative guidance is superseded here.

### D32 addendum — V0 scope narrowed to project + user only

**Trigger:** Three user clarifications landing immediately after D32 was written:
1. "We have a system wide cache I think." — mars already has system-wide infrastructure for source caching, which is fine and doesn't affect this discussion.
2. "System wide is V2 or V3, I don't think we need to care about it." — system scope is explicitly out of V0 scope.
3. "System wide is controlled by the individual harnesses themselves, I don't want to have to deal with that complexity right now." — meridian-channel/mars do not try to manage or unify harness-native global state. Each harness has its own conventions; they coexist.

**V0 mars scopes, narrowed:**

- **Project scope** (default) — `.agents/` in the project tree. This is where most installs land.
- **User scope** (opt-in) — `~/.config/mars/` or XDG equivalent. For personal methodology skills, default agents, cross-project domain packs.
- **System scope** — **deferred to V2/V3.** Reserved as an extension point in the schema per D27, but not implemented, not designed in detail, not part of V0 mental model. If the design-orchestrator for mars-capability-packaging starts spending time on system scope, push back.

**Harness-native global state is not our problem:**

Claude Code has `~/.config/claude/` or wherever it keeps plugins. Codex has its own state. OpenCode has its own. Each harness handles its own global state its own way, and mars makes **no attempt to override, unify, or suppress it**. The interaction rule is simple: **mars's project+user state and the harness's native global state coexist.** If the user has Claude Code plugins installed globally, those are still visible to meridian-launched Claude Code spawns. Mars adds its own capabilities on top via `--mcp-config` and friends.

D31's "bleed-through problem" stops being a problem we have to solve. It becomes "the user has their Claude Code configured however they configured it, and that's fine." If a user wants isolation from their own Claude globals, that's a harness-adapter-level feature request they can bring to us later — not a V0 blocker.

**The cache thing:**

Mars's existing system-wide cache (for downloaded package sources, similar to `~/.cache/uv/`, `~/.cache/pip/`, `~/.cache/cargo/`) is fully compatible with D32 because **caches are not loaded state**. The cache holds source bytes on disk for performance; it doesn't affect what capabilities any project activates, what context any agent sees, or what tools any harness loads. Loaded state (agents, skills, MCPs, CLI-deps) is scoped per D32; cached bytes are infrastructure. The two concerns are orthogonal.

**Net V0 mental model for mars-capability-packaging:**

- Two install scopes: project (default), user (opt-in).
- One activation model: project opts in to user-scoped packs explicitly.
- Zero attempt to manage or suppress harness-native global state.
- Existing system-wide cache is fine; it's not part of the scoping design.
- System scope as an install destination is deferred; reserve the extension point, don't design it.

The receiving dev-orchestrator for mars-capability-packaging should explicitly treat "can mars install into system scope?" as a V2/V3 question and refuse to engage with it in V0 design.

## D33 — Unify meridian-channel spawn/session under HarnessAdapter, refactor hard and early (resolves Q7)

**Date:** 2026-04-08
**Trigger:** User resolution of Q7. Q7 was the question of whether meridian-channel's existing spawn/session mechanism should be rewritten to route through the same `HarnessAdapter` abstraction that the agent-shell-mvp researcher-track work consumes. The correction pass (p1150) left Q7 as an explicit open question in `design/strategy/overview.md` pending a user decision. User's answer: **yes, refactor hard and early.**

**Decision:** meridian-channel's current spawn and session mechanism is refactored to consume the same `HarnessAdapter` interface defined in the agent-shell-mvp design corpus. Both the developer-track (CLI spawns) and the researcher-track (shell spawns) run on a single unified harness layer. The refactor is explicitly part of V0 work, not V1 — done hard, done early, not deferred to a "clean it up later" cycle.

**Why this matters strategically** (and why deferring it would have been wrong):

- **D23's "same packages, different runtime" becomes literally true.** If the developer-track meridian-channel spawns and the researcher-track shell spawns route through different harness layers, a mars pack that works on one track might need translation to work on the other. With unification, a pack that works in one runtime works in both — the adapter is the only variable, and the adapter is shared.
- **D29's SRP/SOLID constraint demands it.** If two code paths reach into harness process management independently, the harness concern is leaking across two boundaries that D29 says should be one. The refactor collapses the duplication.
- **D30's highest-granularity rule compounds.** When mars ships capabilities to the "shell," the "shell" needs to be one concept, not two (CLI shell and GUI shell with different loaders). One adapter layer means one loader, which means `mars add tdd-pack` produces identical runtime behavior regardless of whether the user is running a CLI spawn or a GUI shell session.
- **Mid-turn injection becomes a universal primitive.** The `HarnessAdapter.send_user_message()` method from the D26 / findings-harness-protocols.md work is defined once in the abstraction. When meridian-channel's spawn mechanism routes through the adapter, `meridian spawn inject <spawn_id> "message"` works across Claude, Codex, and OpenCode without any adapter-specific code in the CLI surface. The CLI command is five lines calling the adapter; the adapter handles the wire mechanism per harness.
- **D28's "published wire contracts from V0" gets cheaper.** If only one consumer (the shell) uses the HarnessAdapter, the protocol can be sloppy about versioning because there's only one caller to update. If two consumers use it, the protocol is forced into discipline from day one — which is exactly what we want for an abstraction this load-bearing.

**Why "hard and early" specifically:**

Deferring this refactor to V1 would mean shipping meridian-channel's legacy spawn mechanism alongside the shell's new HarnessAdapter consumption, letting them diverge for weeks or months, and then paying an enormous reconciliation tax when V1 forces them back together. **The reconciliation cost compounds with the amount of code that gets written against each path.** Every new meridian-channel feature that touches spawn/session state during the gap either has to be written twice or has to be rewritten during reconciliation. Every new agent-shell feature that depends on adapter behavior that doesn't yet exist in the CLI path creates an implicit coupling we'll discover the hard way.

Doing it hard and early has a real cost — V0 takes longer than it would if we just shipped the shell on top of a fresh adapter layer and left meridian-channel alone. But the cost is bounded (we know what needs to change; it's a focused refactor, not a research project) and the benefit is permanent (unified substrate, no divergence debt, mid-turn injection as a V0 primitive).

This is the direct application of dev-principles "refactor continuously, not in batches." The accumulated decisions D21–D32 made it obvious that meridian-channel and the shell belong on the same substrate. The refactor is the mechanism that makes that obvious fact true in the code.

**Scope of the refactor:**

1. **Define the unified `HarnessAdapter` protocol** — already partly done in `design/harness/abstraction.md` by the correction pass. Finalize as a published contract with the V0 methods: `launch`, `resume`, `terminate`, `start_turn`, `interrupt_turn`, `send_user_message`, `submit_tool_result`, `capabilities`, `events`, `respond_to_approval`. Version the protocol at 1.0.
2. **Implement adapters for Claude / Codex / OpenCode** against the unified protocol. Claude is V0 primary (per the existing agent-shell-mvp scope); Codex and OpenCode are V1 targets but the adapters should at least be skeleton-implemented to prove the abstraction doesn't warp around Claude.
3. **Rewrite meridian-channel's spawn mechanism** in `src/meridian/lib/harness/` (and wherever else spawn state lives) to consume the adapter layer instead of its current direct-subprocess model. The existing harness code becomes either (a) the implementation behind the Claude adapter, (b) a helper library the adapters share, or (c) deleted in favor of a cleaner reimplementation — whichever the refactor-reviewer and impl-orchestrator decide during planning.
4. **Regression-test every existing meridian-channel workflow.** The dev-workflow orchestrators, the CLI spawn commands, session resume, work items, models routing — all must continue to function through the adapter layer. This is a smoke-test-heavy phase; no existing behavior should regress.
5. **Ship mid-turn injection as a user-facing primitive.** `meridian spawn inject <spawn_id> "message"` becomes a V0 CLI command that works across all implemented adapters. Claude first (queue-to-next-turn semantics), Codex and OpenCode as their adapters land.
6. **Update mars's per-harness config emission** — since mars now emits config for adapters (not raw harnesses), the output contract aligns with the HarnessAdapter abstraction. This is a small change to the mars work item's design scope, worth flagging to the receiving dev-orchestrator.

**Implication for the mars-capability-packaging work item:**

The receiving dev-orchestrator needs to know that adapters are the direct consumer of mars config emission, not raw harnesses. The emission format should be adapter-friendly, not harness-friendly. In practice this may mean a single unified config schema rather than three per-harness formats, with each adapter translating to its native format internally. The `mars-capability-packaging` requirements.md needs a line about this.

**Implication for the planner phase:**

The refactor becomes its own phase (or a set of phases) in the implementation plan. Phase ordering:

1. Finalize HarnessAdapter protocol (design-complete after follow-up correction pass)
2. Build Claude adapter against the new protocol
3. Migrate meridian-channel spawn mechanism to consume the adapter
4. Regression-test existing workflows
5. Ship mid-turn injection primitive
6. ...then proceed with the rest of the agent-shell-mvp V0 implementation phases

The planner should treat phases 1–5 as a hard prerequisite for the shell backend work. The shell can be designed in parallel but cannot be *implemented* until the adapter layer is live, because it consumes the adapter.

**Implication for phase staffing per D29:**

Every phase boundary in the refactor has a `@refactor-reviewer` pass, not just the final loop. The refactor's whole point is collapsing duplication and leaking-abstraction debt; we need continuous structural review to make sure we don't accidentally create new leakage during the work. This is exactly the case where D29's "refactor continuously" rule earns its keep.

**Implication for the follow-up correction pass:**

`design/strategy/overview.md` must close the Q7 open question with D33's answer. The correction pass I was going to spawn for D29/D30/D32 additions now also needs to resolve Q7. This is the last open question in the strategic phase as far as I can tell — the post-correction design corpus should reflect a fully-settled strategy.

**The "refactor hard and early" principle, as a general rule:**

D33 also reinforces a broader commitment that should govern all subsequent meridian-channel development: when the strategic picture reveals that two code paths should be one, or that an abstraction is leaking, **do the refactor immediately, not after more features land on top.** Deferred refactors compound. Early refactors are cheap. This is in dev-principles already, but D33 makes the commitment concrete for the Q7-shaped decisions specifically: accumulated duplication gets resolved the moment it's recognized, not the next sprint.

---

## D34 — agent-shell-mvp is meridian-channel's GUI, not a new product
2026-04-08, supersedes D21. See `reframe.md` for full architectural restatement.

**Decision**: The "agent-shell-mvp" is not a new product that replaces meridian-flow. It is a **local deployment shape** that shares meridian-flow's frontend contract (AG-UI event taxonomy, three-WS topology, activity stream reducer, thread model, per-tool behavior config) but uses **meridian-channel as the agent runtime** instead of direct LLM calls via meridian-llm-go.

**Why the original framing was wrong**: D21 treated agent-shell-mvp as a BYO-Claude replacement for meridian-flow. On closer inspection, meridian-flow and agent-shell-mvp serve different audiences with different deployment shapes:

- **meridian-flow (cloud)**: biomed researchers without their own API keys. Go backend, Daytona sandbox, direct Anthropic/OpenRouter calls via meridian-llm-go, multi-user, hosted.
- **agent-shell-mvp (local)**: developers and prosumers who already own Claude Code. Same Go backend + frontend, but backed by meridian-channel as a subprocess, with harness-managed LLM calls on the user's own subscription.

The two share a frontend codebase and a wire contract but differ in backend composition. meridian-flow is NOT replaced; it's a sibling deployment to the new local path.

**What this means for the work item**:
- Almost every "agent-shell-mvp designs its own frontend/strategy/extensions/packaging" concern disappears.
- The frontend contract lives in `meridian-flow/.meridian/work/biomedical-mvp/design/frontend/` as the canonical source.
- The `agent-shell-mvp/design/` tree collapses to just the meridian-channel refactor scope (harness adapter normalization + streaming spawn mode).
- D22–D30 strategic decisions still stand conceptually but belong at product-strategy level, not in this design.

**Alternatives rejected**:
- *Replace meridian-flow entirely with the shell* — abandons the cloud deployment's audience (researchers without subscriptions).
- *Build the shell on a fresh Go backend that doesn't reuse meridian-flow* — throws away the frontend contract, event taxonomy, WS topology, and reducer that already exist in meridian-flow.
- *Keep shell's own frontend design* — duplicates work and creates two wire contracts to maintain in divergence.

---

## D35 — meridian-channel stays Python, no Go rewrite
2026-04-08

**Decision**: meridian-channel is the agent runtime for the local deployment path and stays in Python. It is not rewritten in Go, not ported incrementally to Go, and not bifurcated into a Go streaming core with a Python control plane. It stays as one Python codebase that grows the capabilities the refactor requires.

**Why**: meridian-channel IS the agent runtime — it owns agent profiles (YAML frontmatter + markdown), skills loading, model resolution, harness selection, work item context, mars integration, spawn/session state, permissions, approval modes, and the CLI surface developers already use in production for dev-workflow orchestration. Rewriting this in Go would be a 2-month+ effort to rebuild something that's already dogfooded and working.

The earlier motivation for considering a rewrite was "so meridian-channel can import meridian-stream-go and meridian-llm-go directly." On closer inspection:
- meridian-channel doesn't need meridian-llm-go at all — the harness owns LLM calls, not meridian-channel.
- meridian-channel would benefit from meridian-stream-go's `InterjectionBuffer` and WS fan-out concepts, but these are ~100–200 lines of Python each, not worth a rewrite for.
- The "shared harness adapter code" concern evaporates once we recognize that meridian-llm-go's providers handle *direct API calls* while meridian-channel's harness adapters handle *subprocess-managed harnesses*. They don't overlap.

**What this means**:
- meridian-channel grows the capabilities it needs (streaming spawn mode, stdin control protocol, AG-UI event emission, per-tool behavior config) as additive Python modules.
- The Go ↔ Python process boundary between meridian-flow's backend and meridian-channel is a clean subprocess with stdin/stdout JSONL. No cross-language FFI, no shared library, no co-located runtimes.
- When Go and Python both implement the same concept (e.g. interjection buffer), they implement it independently in their own idioms. The AG-UI event schema is the wire contract that forces agreement; the implementation languages are deployment details.

**Alternatives rejected**:
- *Full Go rewrite of meridian-channel* — too expensive, too risky, no meaningful benefit. Freezes a working tool for months.
- *Hybrid (Python control plane + Go streaming sidecar)* — two runtimes to deploy, weird boundary, Python's asyncio is adequate for conversational throughput.
- *Rewrite only the harness adapters in Go (keep the rest Python)* — creates a Python-Go boundary inside meridian-channel itself, which complicates deployment and gains nothing.
- *Add a `providers/claude-code/` family in meridian-llm-go that shells out to the harness* — see D40. Puts the subprocess adapter at the wrong layer and loses access to meridian-channel's agent runtime (profiles, skills, model resolution).

---

## D36 — AG-UI event taxonomy is the canonical output schema
2026-04-08

**Decision**: The canonical event schema emitted by meridian-channel's streaming spawn mode is the **AG-UI event taxonomy** from `meridian-flow/.meridian/work/biomedical-mvp/design/frontend/data-flow.md` and `streaming-walkthrough.md`. This supersedes the speculative `normalized-schema.md` draft in agent-shell-mvp's pre-reframe `design/events/`.

**Event types meridian-channel's harness adapters must emit**:

- `RUN_STARTED`, `RUN_FINISHED` — spawn lifecycle boundaries
- `STEP_STARTED` — turn boundaries within a spawn
- `THINKING_START`, `THINKING_TEXT_MESSAGE_CONTENT` — agent reasoning deltas (harness-dependent; Claude exposes thinking, others may not)
- `TEXT_MESSAGE_START`, `TEXT_MESSAGE_CONTENT`, `TEXT_MESSAGE_END` — assistant text output
- `TOOL_CALL_START`, `TOOL_CALL_ARGS`, `TOOL_CALL_END` — tool invocation lifecycle
- `TOOL_OUTPUT` with `stream: stdout|stderr` — tool execution output (streaming)
- `TOOL_CALL_RESULT` — tool completion with final result
- `DISPLAY_RESULT` with `resultType` — structured tool results (text, markdown, image, table, mesh_ref, etc.)

**Per-tool behavior config**: each tool declares render defaults that drive frontend display (input collapsed/visible, stdout visible/collapsed/inline). meridian-channel's harness adapters emit events with the config meridian-flow's reducer already expects — bash collapsed by default, Read/Grep/Glob collapsed, Python stdout inline, etc. The adapter knows per-tool config for its harness's tool set and attaches it to `TOOL_CALL_START` events so the reducer can apply it without special-casing.

**Why**:
- There's a real implementation and a real frontend consuming this schema already in meridian-flow. Inventing a parallel schema for agent-shell-mvp would create two wire contracts to maintain and diverge.
- `frontend-v2` already has an activity stream reducer that ingests these events with correct per-tool collapse defaults. Reusing that reducer is the single largest frontend savings.
- The "conversation tool behaviors" concept raised by the user in-session IS the per-tool render config. Not a new concept, not a new design doc — pointer to existing work.

**Alternatives rejected**:
- *Invent a new normalized schema for agent-shell-mvp* — duplicates existing work, creates translation layers between two custom schemas.
- *Use harness-native stream-json as the wire format directly* — each harness speaks a different dialect; no frontend can cleanly consume three formats.
- *Define schema in agent-shell-mvp, require meridian-flow to adopt* — reverses the dependency and imposes migration cost on meridian-flow's working code.

---

## D37 — Streaming spawn mode + stdin control protocol
2026-04-08

**Decision**: meridian-channel gains a **streaming spawn mode** designed for backend consumption, with a bidirectional stdio control protocol:

**Invocation** (exact flag/subcommand name decided during design):
```
meridian spawn --stream -a <agent> -p <initial prompt>
```

**Stdout**: JSONL stream of AG-UI events (per D36). One event per line.

**Stdin**: JSONL control channel. Control message types:
```json
{"type": "user_message", "text": "wait, reconsider X"}
{"type": "interrupt"}
{"type": "cancel"}
```

`user_message` is the mid-turn injection primitive. `interrupt` stops the current turn without cancelling the spawn. `cancel` terminates the spawn entirely.

**Lifecycle**: process runs until the agent finishes naturally, stdin is closed, or a cancel arrives. On cancellation, the harness adapter tears down the harness subprocess cleanly (SIGTERM with timeout, then SIGKILL).

**Mid-turn injection semantics per harness** (adapter hides the difference; caller sees unified `user_message`):

- **Claude Code**: write stream-json user message frame to harness stdin; Claude queues to the next turn boundary
- **Codex app-server**: call JSON-RPC `turn/interrupt` then `turn/start` with the new message as the initial prompt
- **OpenCode**: POST to the session's message endpoint

**Capability reporting**: the adapter emits a `CAPABILITY` AG-UI event on spawn start declaring its mid-turn injection semantic (`queue` | `interrupt_restart` | `http_post` | `none`). The frontend uses this to render the right affordance — grayed input box with "queued for next turn" vs. a "this will interrupt the current turn" warning vs. a normal send button. Don't lie about wire-level behavior to fake uniformity.

**`meridian spawn inject <spawn_id> "message"` CLI primitive**:

Separate top-level CLI command for injecting mid-turn messages from another process. Two consumers:
1. **Existing dev-workflow orchestrators** (dev-orchestrator, design-orchestrator, impl-orchestrator) — steer children mid-execution from the orchestrator's own session. This validates the abstraction works end-to-end and immediately gives dogfood value.
2. **meridian-flow's Go backend** — forwards frontend user messages to the running agent turn via the injection CLI (or directly via the streaming spawn's stdin, whichever is cleaner; TBD during design).

Underneath, `meridian spawn inject` writes a `user_message` control frame to the spawn's stdin (or to a per-spawn control FIFO in `.meridian/spawns/<id>/` if stdin ownership is complicated by other consumers — design choice).

**Why**: This is the interface between meridian-flow's Go backend and meridian-channel. It's also the interface between dev-workflow orchestrators and their children (mid-turn steering for CLI users, which is useful right now regardless of the shell MVP). One protocol, two consumers — forced into discipline from day one.

**Open questions for the design pass** (not full decisions, enumerated for the @architects):
1. Stdin ownership: does the streaming spawn own its own stdin exclusively, or is there a control FIFO sidecar? The latter decouples "who spawned me" from "who controls me" but adds filesystem primitives.
2. Control message versioning: JSONL with a `version` field from v0.1 so the protocol can evolve additively?
3. Error reporting: when an injected message can't be delivered (e.g., spawn is mid-tool-execution and the harness can't accept input), does the injector get a synchronous error or an async `CAPABILITY_ERROR` event on the spawn's event stream?
4. Integration with existing `meridian spawn wait` / `meridian spawn show` / `meridian spawn log`: does streaming mode change any of those, or is it a parallel invocation shape?

---

## D38 — Scope collapse of agent-shell-mvp design tree
2026-04-08

**Decision**: The existing `agent-shell-mvp/design/` tree is slashed. Under the corrected framing (D34), most of the previous design is either out of scope or duplicates work that lives in meridian-flow.

**Deleted entirely**:

- `design/strategy/` — strategy belongs at product-strategy level, not in a meridian-channel refactor design. D21–D33 remain in `decisions.md` as historical record but are not restated in `design/`.
- `design/extensions/` — composite frontend+MCP interaction-layer extensions are out of scope for the shell MVP. They remain a design goal for the researcher track later, tracked separately.
- `design/packaging/` — mars capability packaging is a separate work item (`mars-capability-packaging`).
- `design/frontend/` — the frontend contract lives in meridian-flow's biomedical-mvp design tree as the canonical source of truth. agent-shell-mvp references it rather than duplicating it.
- `design/execution/` — local execution model collapses to "run as subprocess with stdin/stdout JSONL." Whatever is load-bearing gets absorbed into overview or harness docs.

**Kept but rewritten for the corrected scope**:

- `design/overview.md` — rewritten as a short summary of the corrected architecture: what this work item does, what the external contract is (pointer to meridian-flow), what the deliverables are (D36/D37), what's explicitly NOT in scope.
- `design/harness/` — core deliverable. Rewritten to focus on "meridian-channel harness adapter refactor to emit AG-UI events and support stdin control messages." Files: `overview.md`, `abstraction.md`, `adapters.md`, `mid-turn-steering.md`.
- `design/events/` — rewritten to describe AG-UI translation at the adapter boundary rather than invent a schema. `normalized-schema.md` is replaced with harness → AG-UI mapping tables (one per harness). `flow.md` traces the AG-UI event sequence during a spawn lifecycle.

**Preserved as historical record** (not deleted):

- `requirements.md` — pre-D34 requirements; superseded but preserved for context and to avoid destroying earlier agent work.
- `synthesis.md` — pre-correction convergence output from p1101. Historical.
- `decisions.md` — full log D1–D40; new entries append at the bottom.
- `findings-harness-protocols.md` — authoritative reference for harness protocol capabilities. Still valid.
- `correction-pass-brief.md`, `correction-review-brief.md` — earlier correction artifacts, useful as examples for future correction passes.
- `reviews/`, `exploration/` — historical artifacts from prior design rounds.

**Why**: The pre-reframe tree was designed under D21's wrong assumption (agent-shell-mvp = new product with its own frontend, strategy, extensions, packaging). Under D34, most of it is out of scope or duplicates work in meridian-flow. Keeping the old content live creates drift between what the docs claim and what the work item is actually doing.

**Alternatives rejected**:
- *Keep the old tree as "deprecated" documentation* — noisier than deletion, and agents would have to parse what's current vs. deprecated on every read.
- *Rewrite everything in place* — loses the git history signal that "a reframe happened here" and makes it harder to audit the correction.

---

## D39 — Workstream split across repositories
2026-04-08

**Decision**: The corrected scope splits into three workstreams across two repositories:

1. **meridian-channel D33 refactor** (this work item, rescoped): harness adapter AG-UI normalization (D36), streaming spawn mode + stdin control protocol (D37), `meridian spawn inject` CLI primitive. Lives in `meridian-channel/.meridian/work/agent-shell-mvp/`.

2. **meridian-flow backend 3-WS refactor + meridian-channel subprocess adapter**: `issue #8` (rename existing handlers, add Project WS handler) plus a new "meridian-channel subprocess adapter" in the backend that launches meridian-channel in streaming spawn mode, tails AG-UI events from stdout, and forwards frontend user messages to stdin. Lives in `meridian-flow/.meridian/work/` — meridian-flow's dev-orchestrator decides whether to fold into `biomedical-mvp` or start a new work item.

3. **meridian-flow local deployment path**: localhost binding, Supabase/Daytona optional, static frontend-v2 serving, Converse mode as primary. Could be folded into workstream 2 or stand alone in meridian-flow's work tree. meridian-flow's dev-orchestrator decides.

**Coupling between workstreams** — only two published contracts:

1. **AG-UI event schema** — defined by meridian-flow's biomedical-mvp design, emitted by meridian-channel, consumed by meridian-flow backend + frontend.
2. **Streaming spawn control protocol** — defined in D37, emitted/consumed on meridian-channel's stdout/stdin by the backend subprocess adapter.

Both sides progress in parallel as long as both contracts are respected.

**Why**: Each repo has its own work-tree discipline, its own dev-orchestrator cadence, its own review culture. Putting all three workstreams in meridian-channel's work tree cross-contaminates design state and makes coordination harder. Putting them in meridian-flow's tree would require meridian-flow's design-orchestrator to understand meridian-channel internals.

**Alternatives rejected**:
- *Single work item spanning both repos* — doesn't fit the work-tree model, makes status tracking confusing.
- *One repo drives both sides* — couples release cadences unnecessarily.

---

## D40 — No providers/claude-code/ in meridian-llm-go
2026-04-08, supersedes mid-conversation speculation about adding a harness provider family to meridian-llm-go.

**Decision**: The shell path does not go through meridian-llm-go. There is no new `providers/claude-code/` (or `providers/harness/`, or similar) family in meridian-llm-go for agent-shell-mvp.

**Why**:
- meridian-llm-go's `Provider` interface is designed for direct API calls (HTTPS to Anthropic, OpenRouter, etc.). The shell path runs the LLM inside the harness (Claude Code) on the user's machine, not via a direct API call from the backend. Shoehorning this into meridian-llm-go's `Provider` interface would distort the interface to cover a fundamentally different process model.
- The shell path's backend work belongs at the **backend integration layer**, not the LLM-library layer. meridian-flow's backend already has a concept of different execution paths (direct API + Daytona sandbox, today); a "meridian-channel subprocess" path is a peer to those, not a Provider.
- A hypothetical `providers/claude-code/` would have to either reimplement agent profile / skill / model / harness resolution in Go (rewriting meridian-channel), or shell out to meridian-channel (which is the same subprocess-adapter pattern just buried one layer lower). Both are worse than having the subprocess adapter live at the backend layer where it belongs.

meridian-llm-go stays **as-is** for meridian-flow's current cloud-hosted biomedical-mvp path (direct Anthropic + Daytona). Two paths in meridian-flow's backend, one frontend, no overlap between the LLM library and the agent runtime.

**Alternatives rejected**:
- *Add `providers/claude-code/` that shells out to `claude --input-format stream-json ...` directly* — loses access to meridian-channel's agent runtime (profiles, skills, model routing, work item context, mars integration). The shell's whole point is spawning agents, not raw harness sessions.
- *Add `providers/meridian/` that shells out to `meridian spawn`* — same subprocess adapter, just at the wrong layer. Adds a `meridian-llm-go` ↔ `meridian-channel` dependency that doesn't need to exist.

---

## D41 — MVP reframe: bidirectional streaming foundation, 3-phase delivery, all three harnesses
2026-04-08, supersedes D34–D40 scope framing and the existing requirements.md Decision 4.

**Decision**: The agent-shell-mvp is delivered as **three sequenced phases**, with the universal foundation being "every single spawn in meridian-channel can stream inputs as well as outputs, across all three tier-1 harnesses":

1. **Phase 1 — Bidirectional streaming foundation + smoke tests.** Every harness adapter (Claude Code, Codex, OpenCode) gains input-channel writability while the subprocess is reading from output. Always available, not an opt-in flag, not a new invocation shape — fire-and-forget spawns still work exactly as they do today if the caller ignores the input side. Gate is "all three harnesses pass end-to-end smoke tests for mid-turn injection."
2. **Phase 2 — Python FastAPI WebSocket server** that uses the Phase 1 layer to host an AG-UI event stream over WebSocket, with inbound `user_message` / `interrupt` / `cancel` frames routed to the spawn's input channel. Gate is "smoke tests (end-to-end WebSocket) and unit tests (harness-wire-format → AG-UI mapping in isolation) both green."
3. **Phase 3 — React UI** (`meridian app`), adapted from `frontend-v2`, consuming the Phase 2 WebSocket. Gate is "a single customer can run `meridian app` and interact with a Claude Code spawn end-to-end."

Everything else — Codex/OpenCode parity *in the UI*, permission gating, session persistence, Go CLI rewrite, consolidation of scattered code across the four parallel repos, PyVista interactive tool harness beyond V0-minimum — is tracked in the `post-mvp-cleanup` work item and touched only after the customer validates the direction.

**Scope change vs. existing requirements Decision 4**: The old framing was "V0 Claude Code only, V1 adds OpenCode, Codex deferred indefinitely because exec mode is single-shot." This is superseded: **all three harnesses land in Phase 1**, because the foundation is "every spawn streams bidirectionally" and the foundation can't be half-built without leaving per-harness hacks in the layer above. Codex mid-turn works through its app-server path (JSON-RPC `turn/interrupt` + `turn/start`), not through `codex exec` — per `findings-harness-protocols.md`. Phase 3 (the UI) can still legitimately ship Claude-only first and add the others incrementally, since by then the foundation is uniform.

**Scope change vs. D34–D40**: Those decisions framed the work as "meridian-channel refactor so a separate Go backend (meridian-flow) can consume its output." That framing added the FIFO control protocol, the AG-UI-as-wire-contract-between-languages, and the `meridian spawn inject` CLI primitive as the central deliverables. Under the reframed MVP, there is no separate Go backend during MVP — the Python FastAPI server runs in-process with the spawn manager. Control can be an asyncio queue, not a FIFO. `meridian spawn inject` is still valuable for CLI-to-CLI injection (dev-workflow orchestrators steering children from other shells) but is no longer architecturally central.

**Why**:
- The user's repeated framing in the reframe conversation (c1135+): "primary foundation is to move launch EVERY SINGLE SPAWN WITH THE ABILITY TO STREAM INPUTS AS WELL AS OUTPUTS" and "make sure this works well with all harnesses first." The universality of the foundation is the point.
- The 2-repo Go-backend architecture from D34–D40 was building the right capability for the wrong deployment model. Single customer validation on localhost does not need a cross-language wire protocol; it needs one Python process that handles everything in-process.
- The existing `requirements.md` (from c1046, earlier today) already had most of the right ideas — Python FastAPI + WebSocket, local-only, frontend-v2 in this repo, SOLID harness abstraction — and those are preserved. The 3-phase framing makes the sequencing explicit and gives each phase a verifiable gate.

**Alternatives rejected**:
- *Claude-Code-first, other harnesses in later phases*: lets Phase 1 "land" before the foundation is actually uniform, which means Phase 2 and Phase 3 get written against a Claude-shaped abstraction that then has to be retrofitted for Codex and OpenCode. Cheaper up front, more expensive overall.
- *Ship UI first, fix harness layer later*: inverts the dependency. The UI depends on the foundation being real; shipping UI against a not-yet-bidirectional layer would require mock harnesses in tests and stubbed inject paths in code — both of which would then have to be ripped out.
- *Keep D34–D40 framing as-is and shoehorn the MVP into it*: forces a FIFO control protocol and cross-language wire contract for a single-process Python MVP. Pure complexity tax.

---

## D42 — WebSocket transport for Phase 2 (over SSE + POST)
2026-04-08

**Decision**: Phase 2's FastAPI server uses **WebSocket** as its transport, not Server-Sent Events with a sibling POST endpoint.

**Why**:
- **Single endpoint / single lifecycle / single frame format.** `/ws/spawn/{id}` handles both outbound AG-UI events and inbound `user_message` / `interrupt` / `cancel` frames. The SSE+POST alternative means two endpoints, two auth checks, two failure modes, and two wire formats (SSE `data:` framing vs JSON request bodies) for one logical protocol.
- **Matches user intent.** The user asked for "bidirectional" explicitly. WebSocket is bidirectional natively; SSE is unidirectional with a sidecar POST as a workaround.
- **Matches the existing Go server.** `meridian-flow/backend/internal/service/llm/streaming/` already uses WebSocket. When the post-MVP Go rewrite replaces the Python MVP server with the real Go server, the wire contract stays identical and the React UI doesn't need to change.
- **`ag_ui.core` event types work over any transport.** The `ag_ui.encoder.EventEncoder` is specifically an SSE framer; skipping it costs one line per event (`event.model_dump_json(by_alias=True, exclude_none=True)`). The Pydantic models — which are the valuable part — are transport-agnostic.

**Cost**: WebSocket requires manual reconnect logic on the client side (~20 lines of TypeScript, the `ReconnectingWebSocket` pattern). Deferred to post-MVP polish; single-customer validation can accept "refresh if disconnected" for the first release.

**Alternatives rejected**:
- *SSE outbound + POST inbound*: conceptually simpler in isolation but operationally more complex — two surfaces, two failure modes, two wire formats. Wrong trade for a localhost single-user MVP.
- *SSE only*: loses bidirectional, breaks the entire premise of the work item.
- *Raw TCP / custom framing*: hostile to browsers, no upside over WebSocket for this use case.

---

## D43 — Adopt `ag-ui-protocol` Python SDK for event types
2026-04-08

**Decision**: Phase 2 uses the `ag-ui-protocol` PyPI package as the source of truth for AG-UI event types and serialization, rather than porting `events.go` / `emitter.go` from the Go server by hand.

**What the SDK gives us**:
- `ag_ui.core` — all AG-UI event types as Pydantic models: `RunStartedEvent`, `TextMessageStartEvent/Content/End`, `ToolCallStartEvent/Args/End/Result`, `StateSnapshotEvent`, `StateDeltaEvent`, `MessagesSnapshotEvent`, `StepStartedEvent/Finished`, `ReasoningStart/Content/End`, `RunFinishedEvent`, `RunErrorEvent`, plus `RAW` and `CUSTOM` escape hatches.
- Pydantic validation and `model_dump_json(by_alias=True, exclude_none=True)` for protocol-compliant camelCase serialization.
- `ag_ui.encoder.EventEncoder` for SSE framing (not used in Phase 2 since we picked WebSocket per D42, but kept available).
- Automatic forward-compatibility with upstream AG-UI spec evolution.

**What the SDK does NOT give us**:
- The **mapping from harness wire format to AG-UI events**. The Go server's mapping is for HTTP-API streams (Anthropic Messages API, OpenRouter) — it is not a harness-subprocess mapping. The Python MVP still has to write a Claude-stream-json → AG-UI mapper, a Codex-JSON-RPC → AG-UI mapper, and an OpenCode-wire → AG-UI mapper from scratch. This is the bulk of Phase 2's real work.

**Role of the Go server** (`meridian-flow/backend/internal/service/llm/streaming/`): reduced from "code we port" to **semantic reference only**. When writing the harness-to-AG-UI mappers, the design team reads `emitter.go`, `stream_executor.go`, `block_processor.go`, `tool_executor.go`, `cancel_handler.go`, and `catchup.go` to understand when to emit which event, how state snapshots interact with message deltas, how tool calls order relative to text content, and how reconnect/catchup behaves. But the types themselves come from the Python SDK.

**Reference implementation to inspect**: `agent-framework-ag-ui` on PyPI (released April 2026) already has the "orchestrator → event bridge → FastAPI SSE endpoint" shape. Not adopted as a dependency, but worth reading as a template for how the pattern looks in idiomatic Python.

**Why**:
- Porting `events.go` by hand is lossy, duplicative, and guarantees drift from upstream AG-UI as it evolves.
- Pydantic gives us validation, type safety, and JSON schema export for free — all of which we'd have to rebuild if we rolled our own types.
- The frontend-v2 React components already speak AG-UI, so using the canonical Python package guarantees wire compatibility.

**Alternatives rejected**:
- *Port `events.go` to Python by hand*: duplicative, lossy, requires ongoing sync with upstream.
- *Invent our own event taxonomy*: breaks frontend-v2 compatibility and throws away the entire point of using AG-UI.
- *Depend on `agent-framework-ag-ui`*: too much surface area (Agent Framework itself, orchestrator bridge, etc.) for what we actually need — which is just the event types.

---

## D44 — Archive `agent-shell-mvp/design/` subtree entirely, restart from scratch
2026-04-08, supersedes D38's "kept but rewritten for the corrected scope" plan for `design/harness/` and `design/events/`.

**Decision**: The entire `agent-shell-mvp/design/` subtree is archived as of this decision. A fresh design tree is produced from scratch by a new `@design-orchestrator` spawn using the updated `requirements.md` as its input.

**What gets archived (removed from live tree, preserved in git history)**:
- `design/overview.md`
- `design/refactor-touchpoints.md`
- `design/harness/` (overview, abstraction, adapters, mid-turn-steering)
- `design/events/` (overview, flow, harness-translation)
- Any nested content in `design/`

**What stays live at the work item root** (not part of `design/`):
- `requirements.md` — updated in this same decision pass
- `decisions.md` — the authoritative decision log (this file)
- `findings-harness-protocols.md` — authoritative reference for harness mid-turn capabilities; referenced by D41 and must stay accessible to the fresh design pass
- `reframe.md`, `synthesis.md`, `exploration/`, `reviews/`, `correction-pass-brief.md`, `correction-review-brief.md` — historical artifacts from prior rounds, preserved

**Why**:
- The archived tree was built under the D34–D40 framing (meridian-flow as Go backend consumer, AG-UI as cross-language wire contract, FIFO control protocol as the central deliverable). Under D41's reframe, most of those deliverables either don't apply or apply very differently.
- Cherry-picking "still-valid" bits of the old tree creates confusion about what's current vs historical. Fresh design from scratch — using the 3-phase scope and the preserved findings as inputs — is cleaner than incremental repair.
- The fresh `@design-orchestrator` run gets a clean slate and produces a design that is coherent end-to-end against D41, rather than a patchwork of old-framing-with-edits.

**Alternatives rejected**:
- *Incrementally rewrite the existing `design/` files*: guarantees residual old-framing assumptions slipping through. Cheap to do, expensive to audit.
- *Keep the old tree alongside new design as "deprecated"*: two design trees in one work item is confusing and agents waste cycles figuring out which is current.
- *Preserve `refactor-touchpoints.md` as a standalone artifact at work item root*: tempting (the 37-file impact map is factually useful ground truth about the harness layer), but it was mapped against the D34–D40 deliverables. The new design will need its own touchpoints map against the 3-phase scope, and the old one would bias that exercise. Preserved in git history if needed.

---

## D45 — OpenCode adapter uses HTTP, not WebSocket (issue #13388 not merged)
2026-04-09, informed by p1180 research

**Decision**: The Phase 1 OpenCode adapter uses the HTTP session API (`POST /session/:id/message` + `GET /event` SSE), not the proposed `/acp` WebSocket endpoint from issue #13388.

**Why**: Issue #13388 is still open as of 2026-04-09. The HTTP API is the current stable surface exposed by `opencode serve`. Designing against an unmerged proposal would leave the adapter untestable.

**What this means**: The `OpenCodeConnection` implementation is HTTP-based, using `aiohttp` for async HTTP requests and SSE streaming. If #13388 merges later, a transport-layer swap from HTTP to WebSocket is scoped to `opencode_http.py` internals — the `HarnessConnection` protocol insulates everything above it.

**Alternatives rejected**:
- *Wait for #13388 to merge* — blocks Phase 1 indefinitely on an external timeline.
- *Stub the OpenCode adapter* — violates D41's "all three harnesses in Phase 1" commitment.

---

## D46 — Additive architecture: bidirectional path alongside fire-and-forget
2026-04-09

**Decision**: The bidirectional streaming layer is a parallel code path (`harness/connections/` + `streaming/`), not a modification of the existing fire-and-forget launch path (`launch/`). The existing `SubprocessHarness` protocol, `runner.py`, `process.py`, and `stream_capture.py` are untouched.

**Why**: The fire-and-forget path is battle-tested and powers every existing `meridian spawn`. Modifying it risks regressions in all existing dev-workflow orchestration. The bidirectional path has fundamentally different mechanics (WebSocket/HTTP transport vs. subprocess stdio) and doesn't benefit from sharing implementation with the existing path.

**What this means**: A harness now has two implementations: a `SubprocessHarness` (existing) for fire-and-forget spawns, and a `HarnessConnection` (new) for bidirectional spawns. They share the harness ID and capability metadata, but their implementations are independent. This is SRP applied at the concern level — command building is a different concern from bidirectional transport management.

**Alternatives rejected**:
- *Replace the existing launch path with the bidirectional one* — too much risk to existing functionality. The bidirectional path must be proven in the new context before it could ever replace the old one.
- *Refactor both paths into a shared abstraction* — premature unification. The two paths may converge post-MVP, but forcing it now would slow Phase 1 with no user benefit.

---

## D47 — Unix domain socket for cross-process inject (Phase 1)
2026-04-09

**Decision**: Cross-process `meridian spawn inject` communicates with the spawn manager via a Unix domain socket at `.meridian/spawns/<spawn_id>/control.sock`.

**Why**: `meridian spawn inject` runs in a separate process from the one hosting the `SpawnManager`. The socket provides a clean, discoverable control channel. It's filesystem-based (fits files-as-authority), path is deterministic from spawn ID, supports async message passing, and cleans up naturally with spawn artifacts.

**What this means**: Each bidirectional spawn creates a Unix domain socket. The socket protocol is simple JSON request/response — one message per connection. Phase 2's FastAPI server uses the in-process asyncio path directly (no socket needed — same process).

**Alternatives rejected**:
- *Named pipe (FIFO)* — unidirectional, doesn't support request/response without a second pipe.
- *HTTP endpoint per spawn* — heavy for a localhost-only control channel.
- *File-based signaling (write a file, poll for it)* — latency and race conditions.
- *Shared memory / mmap* — overcomplicated for simple JSON messages.

---

## D48 — AG-UI Thinking vs. Reasoning event naming: use THINKING_* with Meridian thinkingId extension
2026-04-09, informed by p1178 research

**Decision**: The Phase 2 AG-UI mapper emits `THINKING_START` / `THINKING_TEXT_MESSAGE_*` events for Claude's thinking blocks, with a Meridian-extended `thinkingId` field. The newer `REASONING_*` event family exists in the SDK but is not used for MVP.

**Why**: The frontend-v2 reducer already consumes `THINKING_START` + `THINKING_TEXT_MESSAGE_CONTENT` with `thinkingId`. The AG-UI SDK exports both families. Switching to `REASONING_*` would require frontend changes for zero user benefit in the MVP. The `thinkingId` extension is a Meridian convention (AG-UI's `ThinkingStartEvent` uses `message_id`, not a dedicated thinking ID) — the Phase 2 mapper generates it and the frontend expects it.

**Alternatives rejected**:
- *Use REASONING_* events* — would require updating frontend-v2's reducer, which adds Phase 3 scope for no user-visible benefit.
- *Use raw AG-UI ThinkingStartEvent.message_id as-is* — breaks frontend-v2 compatibility which expects `thinkingId`.

---

## D49 — Durable drain architecture: one reader per spawn, fan-out to UI clients
2026-04-09, informed by review round 1 (p1182 BLOCKER, p1183 BLOCKER)

**Decision**: The `SpawnManager` runs one durable drain task per spawn that always reads `connection.events()` and persists to `output.jsonl`, independent of any UI client. UI clients subscribe to an `asyncio.Queue` fed by the drain task. They never own the event iterator.

**Why**: Reviewers p1183 (feasibility) and p1182 (design alignment) both identified that the original design's Phase 2 endpoint read `connection.events()` directly in the WebSocket handler's outbound task. A client disconnect would end that task, which stops consuming `connection.events()` — violating the requirement that spawns continue running when the browser disconnects. Output backpressure from a dead WebSocket could stall the harness stream.

The fix is architectural: separate the drain (persistence + fan-out source) from the presentation (UI WebSocket). The drain task is the sole consumer of `connection.events()`. It persists every event to `output.jsonl` before fanning out to subscriber queues. UI clients are consumers of the fan-out, not owners of the drain.

**What this means**:
- `SpawnManager._drain_loop()` runs for the lifetime of each spawn
- `SpawnManager.subscribe()` / `unsubscribe()` manage per-spawn subscriber queues
- Phase 2 endpoint calls `manager.subscribe(spawn_id)` on connect, `manager.unsubscribe(spawn_id)` on disconnect
- MVP: one subscriber per spawn (second connection rejected). Fan-out to multiple subscribers is post-MVP.

**Alternatives rejected**:
- *Read events directly in WS handler*: fails the disconnect requirement — reviewer blocker.
- *Buffer everything in memory, write to disk on spawn completion*: OOM risk on long-running spawns.
- *Two readers (one for disk, one for WS)*: `AsyncIterator` is single-consumer; would require `asyncio.Queue` tee anyway.

---

## D50 — Universal bidirectionality: no "bidirectional" spawn mode
2026-04-09, informed by review round 1 (p1182 BLOCKER)

**Decision**: There is no `kind="bidirectional"` or `launch_mode="bidirectional"` in the spawn store. Every spawn launched after Phase 1 gets a `HarnessConnection` and a control socket. Bidirectionality is universal and always-on per D41 — not a flag, not a mode, not a new invocation shape.

**Why**: Reviewer p1182 identified that the original design introduced `kind="bidirectional"` / `launch_mode="bidirectional"` as a separate spawn mode, which contradicts D41's requirement that "every harness adapter gains the ability to write to the subprocess's input channel... Not a flag. Not a mode." The design's `spawn inject` error message "not a bidirectional spawn" confirmed the violation — existing dev-workflow spawns would not be steerable.

The fix: existing `kind` and `launch_mode` values are unchanged. The presence of `control.sock` in the spawn artifact directory is the discoverable indicator that a spawn accepts injection. Fire-and-forget callers that never use `send_*()` or the control socket get exactly the same behavior as before.

**What changed in design docs**: `phase-1-streaming.md` spawn state recording section, `overview.md` relationship section, `edge-cases.md` inject error messages.

**Alternatives rejected**:
- *Keep bidirectional as a mode, update D41*: contradicts the user's explicit framing in c1135 and the requirements doc. The universality of the foundation is the point.
- *Only add control sockets to spawns started via `meridian app`*: partial universality is worse than no universality — it means `meridian spawn inject` sometimes works and sometimes doesn't with no clear reason.

---

## D51 — Inbound action recording for files-as-authority compliance
2026-04-09, informed by review round 1 (p1182 BLOCKER)

**Decision**: All inbound steering actions (`user_message`, `interrupt`, `cancel`) are durably recorded to `.meridian/spawns/<spawn_id>/inbound.jsonl` before being routed to the harness. Each record includes action type, data, timestamp, and source (websocket vs control_socket).

**Why**: Reviewer p1182 identified that the original design persisted raw harness output, stderr, heartbeat, and connection metadata, but inbound steering actions were routed live to `SpawnManager` with no durable append path. This violated the files-as-authority principle for the most important user interventions — if a user steers a run mid-turn, that decision disappeared from the authority-bearing record.

**What this means**: `SpawnManager.inject()`, `.interrupt()`, and `.cancel()` each call `_record_inbound()` after successful delivery. The `source` field distinguishes WebSocket UI from CLI control socket. `meridian spawn show` can display the inbound action history alongside outbound events.

**Alternatives rejected**:
- *Log inbound actions only to stderr.log*: not structured, not queryable, mixes with harness stderr.
- *Embed inbound actions in output.jsonl*: conflates two different streams (harness output vs user input). Separate files make replay and audit clearer.
- *Record only in memory*: fails the durability requirement.

---

## D52 — Claude transport: --sdk-url primary with explicit compatibility contract and hybrid fallback
2026-04-09, informed by review round 1 (p1183 BLOCKER, p1184 BLOCKER)

**Decision**: The Claude adapter uses `--sdk-url` as its primary bidirectional transport but with an explicit compatibility contract: version gating, protocol mismatch detection, feature flag, and a concrete hybrid fallback path (stdout NDJSON receive + HTTP POST send).

**Why**: Reviewers p1183 and p1184 both flagged `--sdk-url` as high-risk because it's reverse-engineered. p1184 noted an inconsistency with `findings-harness-protocols.md` which mentions stable stdio NDJSON. The original design acknowledged the risk but didn't specify the fallback concretely enough to implement.

The resolution: `--sdk-url` is the right choice for MVP because it gives true bidirectional WS with the simplest event model. But the adapter must fail gracefully and detectably when Claude CLI versions change. The hybrid fallback (receive from stdout NDJSON, send via HTTP POST to `CLAUDE_CODE_POST_FOR_SESSION_INGRESS_V2`) is a concrete alternative that reuses existing fire-and-forget capture infrastructure.

**What this means in design**: `harness-abstraction.md` Claude section now specifies version gating, protocol mismatch detection, feature flag, and hybrid fallback details.

**Alternatives rejected**:
- *Use stdio NDJSON as primary*: loses true bidirectional WS simplicity. stdout capture works for receive but injection via HTTP POST has higher latency and no message ordering guarantee relative to the output stream.
- *Use --sdk-url with no fallback*: single point of failure on an undocumented API.
- *Defer Claude bidirectional entirely*: contradicts D41's "all three harnesses."

---

## D53 — Connection state machine for LSP compliance
2026-04-09, informed by review round 1 (p1184 CONCERN-2)

**Decision**: `HarnessConnection` exposes a `state` property returning `ConnectionState` (a `Literal` enum: created, starting, connected, stopping, stopped, failed). State transitions are documented. `send_*()` methods raise `ConnectionNotReady` if state != "connected". `events()` yields nothing after "stopped" or "failed".

**Why**: Reviewer p1184 identified that without a state machine, adapters would invent their own answers to invalid-state transitions (send before start, send after death, iterate after stop). One adapter would raise, another would silently discard, another would deadlock — an LSP violation that makes adapters non-substitutable. The state machine is a contract, not an implementation — adapters implement it, callers rely on it.

**What changed**: `harness-abstraction.md` now defines `ConnectionState`, transition rules, behavioral contracts per state, and `ConnectionNotReady` exception.

**Alternatives rejected**:
- *Document behavior per-method without a state enum*: still leaves room for adapter divergence since there's no single property to check.
- *Leave it to implementers*: guarantees LSP violation when three adapters each handle edge cases differently.

---

## D54 — Capabilities on HarnessConnection composite, not HarnessReceiver
2026-04-09, informed by review round 1 (p1184 CONCERN-1)

**Decision**: `ConnectionCapabilities` is a property on `HarnessConnection` (the composite protocol), not on `HarnessReceiver`. `HarnessReceiver` is a pure event stream with no capability metadata.

**Why**: Reviewer p1184 identified an ISP violation: capabilities like `supports_interrupt`, `supports_cancel`, and `runtime_model_switch` describe sender-side and lifecycle-side behavior. A consumer that only needs to receive events (log writer, metrics collector) shouldn't depend on an interface exposing send-side capability metadata.

**What changed**: `harness-abstraction.md` moved `capabilities` property from `HarnessReceiver` to `HarnessConnection`.

**Alternatives rejected**:
- *Keep capabilities on HarnessReceiver*: ISP violation — forces receive-only consumers to see send-side metadata.
- *Split into EventCapabilities (on Receiver) and SendCapabilities (on Connection)*: over-engineering for MVP. If a receiver-only consumer genuinely needs event-format info (e.g., whether thinking events appear), that can be extracted later.

---

## D55 — Single capability source: HarnessCapabilities gets only supports_bidirectional boolean
2026-04-09, informed by review round 1 (p1184 CONCERN-4)

**Decision**: The existing `HarnessCapabilities` on `SubprocessHarness` gets only `supports_bidirectional: bool = False`. No `mid_turn_injection` enum on the fire-and-forget side. All bidirectional capability metadata lives exclusively in `ConnectionCapabilities` on `HarnessConnection`.

**Why**: Reviewer p1184 identified dual-source divergence risk: the original design had `mid_turn_injection` on both `HarnessCapabilities` and `ConnectionCapabilities`. If they disagree, which is authoritative? Eliminating the duplicate ensures one place to look for injection semantics.

**Alternatives rejected**:
- *Mirror mid_turn_injection on both*: dual-source divergence when they inevitably drift.
- *Put everything on ConnectionCapabilities only*: need the boolean on `HarnessCapabilities` so code can check "does this harness support bidirectional at all?" without constructing a connection.

---

## D56 — Override D48: use standard AG-UI `REASONING_*` events, not custom `THINKING_*`
2026-04-09, user override of design-orchestrator's D48.

**Decision**: Claude's extended thinking maps to the standard `REASONING_START`, `REASONING_MESSAGE_CONTENT`, `REASONING_MESSAGE_END` events from `ag_ui.core` — not custom `THINKING_*` events. Reasoning and thinking are the same concept. If frontend-v2 uses `THINKING_*` naming internally, rename those references during Phase 3 adaptation to align with the AG-UI standard.

**What this changes**: Phase 2's Claude AG-UI mapper emits `ReasoningMessageStartEvent`, `ReasoningMessageContentEvent`, `ReasoningMessageEndEvent` from `ag_ui.core` instead of custom event dicts. Phase 3 renames any frontend-v2 `THINKING_*` references to `REASONING_*` to match.

**Why**: D43 adopted the `ag-ui-protocol` Python SDK as the canonical source for event types. Diverging from the standard for thinking/reasoning events undermines that commitment. The standard `REASONING_*` events exist for exactly this purpose — there's no semantic gap that justifies custom events.

## D57 — Two-layer WS client: generic WsClient + SpawnChannel
2026-04-09, user direction.

**Decision**: The frontend WebSocket client is split into two layers: a generic `WsClient` (connection lifecycle, JSON frame send/receive, state tracking — no domain knowledge) and a `SpawnChannel` on top (constructs spawn URL, parses AG-UI events, typed send methods). Replaces the plan's monolithic `SpawnWsClient`.

**What this replaces**: Design and plan originally specified a single `SpawnWsClient` that mixed transport concerns with spawn-specific AG-UI logic.

**Why**: If meridian app eventually becomes a cloud service, the WS transport layer needs to support channels beyond spawn streaming (project management, collaboration, etc.). Baking spawn semantics into the transport makes that extension require a rewrite. Generic transport + domain channels is the standard pattern and costs almost nothing extra now.

**Alternatives rejected**: (1) Copy `WsClient` from frontend-v2 — user preferred building our own to avoid carrying frontend-v2's assumptions. (2) Single `SpawnWsClient` — locks the transport to one use case.

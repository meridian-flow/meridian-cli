`meridian report create --stdin` fails here with `error: Unknown command: report`, so here’s the full markdown report as a fallback.

---

# agent-shell-mvp — requirements alignment review (FOCUS: requirements.md)

Date: 2026-04-08

This review audits the design docs under `.meridian/work/agent-shell-mvp/design/` against the contract in `.meridian/work/agent-shell-mvp/requirements.md`, with emphasis on Decisions 1–10, the “must NOT do” list, Q1–Q5, V0 shippability for the Yao Lab μCT validation, and edge-case completeness.

## Requirements compliance matrix (Decisions 1–10)

| Decision | Requirement (summary) | Where covered | Verdict | Notes |
|---|---|---|---|---|
| 1 | Shell lives in `meridian-channel`; copy frontend-v2; no Go backend in V0 | `design/overview.md`, `design/repository-layout.md`, `design/frontend-integration.md` | **Compliant** | Clear commitment to in-repo copy and local-only scope. |
| 2 | FastAPI backend + WebSocket; frontend protocol ↔ harness protocol translator; reuse `.agents/` machinery | `design/overview.md`, `design/frontend-protocol.md`, `design/event-flow.md`, `design/agent-loading.md` | **Partial** | Core topology matches. But upload/staging semantics are inconsistent across docs (see BLOCKER-2). |
| 3 | SOLID harness abstraction (DIP/OCP/ISP/LSP) designed against opencode; adapter swap should not require router/translator changes | `design/harness-abstraction.md` (+ referenced in `design/event-flow.md`) | **Compliant** | Strongly specified with verification checklist and failure modes. |
| 4 | V0 Claude Code only; V1 opencode; Codex deferred | `design/overview.md`, `design/harness-abstraction.md`, `design/event-flow.md` | **Compliant** | V0 fences are explicit; V1 placeholders are present. |
| 5 | Frontend is frontend-v2 copied into repo (not Reflex/Streamlit/etc.) | `design/repository-layout.md`, `design/frontend-integration.md` | **Compliant** | Explicit copy strategy and cut list. |
| 6 | Domain extension via interactive tools (not custom shell panels) | `design/interactive-tool-protocol.md`, `design/frontend-protocol.md` | **Partial** | Mechanism is correct, but interactive tool execution model conflicts with `design/local-execution.md` (BLOCKER-1). Also some frontend text implies adding domain-specific tool detail components (risk; keep default generic). |
| 7 | Local Python venv is analysis runtime; persistent kernel; no Daytona in V0 | `design/local-execution.md`, `design/repository-layout.md` | **Partial** | Persistent-kernel design matches. But tool execution and staging/upload design contradict other docs (BLOCKER-1/2). |
| 8 | Do not rewrite meridian-channel out of Python | `design/overview.md`, `design/repository-layout.md` | **Compliant** | Explicitly deferred/parked. |
| 9 | Files-as-authority → scientific reproducibility; every step I/O captured under work item dir | `design/local-execution.md`, `design/interactive-tool-protocol.md`, `design/event-flow.md` | **Compliant** | Per-turn/per-cell audit layout is detailed and matches crash-only discipline. |
| 10 | Co-pilot with feedback loops (Path A vision self-feedback + Path B interactive correction) | `design/interactive-tool-protocol.md`, `design/frontend-protocol.md`, `design/overview.md` | **Partial** | Path B is well-covered. Path A is described, but `design/overview.md` places it in V1 while `design/interactive-tool-protocol.md` frames it as V0-available via normal `python` + images; docs should align. |

## Open questions matrix (Q1–Q5)

| Question | Requirement | Where addressed | Verdict | Notes |
|---|---|---|---|---|
| Q1 | Relationship to `meridian-flow` (replace vs coexist vs replace eventually) | `design/overview.md` | **Open (correctly)** | Surfaced; not silently resolved. |
| Q2 | V0 scope: mid-turn injection, permission gating, session persistence | `design/event-flow.md` §11, `design/overview.md` | **Open (mostly)** | `design/event-flow.md` recommends V1 for all three (acceptable), but some other docs misuse “Q2” to refer to upload/datasets (MINOR-1). |
| Q3 | Repository layout choice | `design/repository-layout.md` | **Resolved (correctly)** | Chosen and justified (`src/meridian/shell/` + `frontend/`). |
| Q4 | What stays vs cuts in frontend-v2 | `design/frontend-integration.md` | **Resolved (correctly)** | Explicit inventory and cut plan. |
| Q5 | Mid-turn injection design should be opencode-shaped; V0 must not warp abstraction to Claude | `design/harness-abstraction.md`, `design/event-flow.md` | **Compliant** | Abstraction is explicitly opencode-shaped with capability flags. |

## Findings

### BLOCKER

**BLOCKER-1 — Interactive tool execution model contradicts itself across docs**
- **Where:** `design/interactive-tool-protocol.md` §1.2/§8 vs `design/local-execution.md` §12
- **Problem:** `interactive-tool-protocol.md` specifies interactive tools as first-class tools with their own execution path (registry + runner + envelopes) and explicitly argues they should *not* run as a raw `python` call. `local-execution.md` §12 then recommends executing interactive tools *inside the persistent kernel* (in-kernel wrapper), not as a separate subprocess/envelope-driven runner.
- **Impact:** Implementers cannot build a coherent V0. This choice affects: cancellation semantics, how tool schemas are surfaced to the harness, whether tools can access in-memory vs file state, and what is persisted as the audit trail.
- **Suggestion:** Pick one execution model and update **all** affected docs (`event-flow.md`, `frontend-protocol.md`, `interactive-tool-protocol.md`, `local-execution.md`) so the end-to-end story is singular. My bias: prefer the envelope/runner model for crash-only + reproducibility + domain neutrality, and ensure performance by standardizing file-based handoff (meshes/volumes) rather than in-memory coupling.

**BLOCKER-2 — Upload/staging design is inconsistent and risks breaking validation step 1 (DICOM ingest)**
- **Where:** `design/local-execution.md` §9 vs `design/frontend-integration.md` §5.1 (upload client), and `design/frontend-protocol.md` §10 (claims “image upload out of scope”)
- **Problem:** `local-execution.md` explicitly rejects presign/manifest upload complexity (local staging only; drag-drop writes bytes directly to `<work-item>/data/raw`). `frontend-integration.md` proposes a presign/PUT/finalize client surface. `frontend-protocol.md` says large inline uploads are V1/out of scope.
- **Impact:** V0 risks shipping without a clear, implementable “Dad loads DICOM stacks” flow, which is the first step of the validation pipeline. It also creates mismatched backend/API expectations.
- **Suggestion:** Decide the V0 ingest UX and document it consistently. Recommendation: V0 = drag-drop (or folder picker) that copies into `<work-item>/data/raw/` via a simple local REST multipart endpoint (no presign/finalize), plus a sidebar file/dataset browser to confirm what landed.

**BLOCKER-3 — Session semantics (multi-tab, reconnect, and “session identity”) are contradictory**
- **Where:** `design/event-flow.md` §10.2, `design/frontend-integration.md` §13 (multi-tab), `design/repository-layout.md` §12 (“Dad closes tab”) and `design/local-execution.md` §10 (“session end”)
- **Problem:** The docs disagree on whether multiple tabs attach to the same session or create separate sessions; whether closing a tab preserves the session; and what “session end” means in V0.
- **Impact:** Backend `SessionManager` keying, frontend UX, and crash-only recovery behavior cannot be implemented correctly without a single definition.
- **Suggestion:** Define one invariant:
  - What is the stable session key? (per work item? per browser connection? explicit “Start session” action?)
  - What happens on WS disconnect in V0 (buffer vs drop vs stop-after-grace)?
  - What is the intended multi-tab behavior (fan-out vs isolated)?
  Then align all edge-case sections to that invariant.

**BLOCKER-4 — “Dad must not touch a terminal” is not satisfied by the current V0 launch story**
- **Where:** `requirements.md` “customer reminder” + `design/repository-layout.md` §4/§9
- **Problem:** The design centers `meridian shell start` as the launch mechanism. That is terminal-first. There is no V0 distribution/launcher plan that lets Dad start the shell without CLI.
- **Impact:** Violates the explicit validation constraint.
- **Suggestion:** Add a concrete V0 “no terminal” launch path (even if minimal): a platform script/app bundle that starts the server and opens the browser, with a one-time installer step handled by someone else. Document it as part of V0, not V1.

### MAJOR

**MAJOR-1 — pnpm/dist expectations conflict (runtime requirements unclear)**
- **Where:** `design/repository-layout.md` §9 + §12 vs `design/frontend-integration.md` §13 (`pnpm` not runtime; expects `dist/` present)
- **Impact:** Packaging and first-run UX are unclear. This directly affects Dad’s experience.
- **Suggestion:** Decide one: (a) ship a prebuilt `frontend/dist` with releases (no pnpm for users), or (b) require pnpm for local installs (document clearly). Don’t mix.

**MAJOR-2 — Risk of over-engineering for V0 in non-load-bearing areas**
- **Where:** `design/frontend-protocol.md` §11 (Pydantic→TS codegen + CI gating), `design/frontend-integration.md` (multiple stores + heavy viewer deps)
- **Impact:** Could slow the “ship V0 to validate pipeline” goal, even if technically nice.
- **Suggestion:** Keep SOLID rigor for harness/translator/agent-loading; for V0, consider manual types or a single shared schema file, and defer CI/codegen strictness until after the first end-to-end demo runs.

**MAJOR-3 — Decision 10 Path A status is inconsistent**
- **Where:** `design/overview.md` §6 (“Path A” listed under V1) vs `design/interactive-tool-protocol.md` §10 (describes Path A as normal V0 `python` + `show_image` + multimodal attachments)
- **Impact:** Planning ambiguity for V0 validation; Path A may be important for reducing reliance on human clicking.
- **Suggestion:** Clarify whether V0 explicitly supports Path A (likely yes if it’s “just python + images”), and if so list it under V0 in `overview.md`.

### MINOR

**MINOR-1 — “Q2” is referenced as if it governs upload/datasets**
- **Where:** `design/frontend-integration.md` §14
- **Impact:** Confuses reviewers/implementers about what Q2 actually is.
- **Suggestion:** Rename that reference; treat upload/datasets as its own explicit decision or add a new “OQ-FE-*” list.

**MINOR-2 — Cross-doc contract drift: interactive tool subprocess vs in-kernel assumptions leak into edge-case sections**
- **Where:** `design/frontend-protocol.md` §7, `design/frontend-integration.md` §13, `design/interactive-tool-protocol.md` §11, `design/local-execution.md` §12
- **Suggestion:** After resolving BLOCKER-1, re-audit all “Edge cases” sections and delete the branches that assume the losing model.

## Edge-case coverage audit (are the “Edge cases” sections comprehensive?)

- `design/harness-abstraction.md` §11: strong coverage (crash, hang, desync, interrupt, WS disconnect buffering, malformed events, approval timeouts, concurrency).
- `design/frontend-protocol.md` §10: good protocol-level coverage (unknown events, seq gaps, binary orphans).
- `design/event-flow.md` §10: good ordering and WS-level cases, but depends on an unambiguous session model (currently contradictory across docs).
- `design/local-execution.md` §14: strong execution-layer failures (kernel death, ENOSPC, Ctrl-C, cwd drift).
- `design/interactive-tool-protocol.md` §11: good human-interaction failures (no display, missing deps, early window close, timeout races).
- `design/frontend-integration.md` §13 and `design/repository-layout.md` §12: many operational edge cases, but contradict each other on build/runtime assumptions and session behavior.

## Verdict

**Request changes** before implementation starts.

The design has strong individual components (especially the harness abstraction and the files-as-authority execution audit trail), but **cross-document contradictions** currently prevent a consistent V0 build plan and put the validation constraints at risk.

## Concrete next steps (minimal set to unblock implementation)

1. Decide and document one interactive-tool execution model (BLOCKER-1).
2. Decide and document V0 DICOM ingest/staging UX (BLOCKER-2).
3. Decide and document V0 session identity + multi-tab + reconnect behavior (BLOCKER-3).
4. Add a V0 “no terminal” launcher story for Dad (BLOCKER-4).
5. After the above, do a single-pass doc consistency sweep to remove stale assumptions.
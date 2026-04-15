# Review Brief — agent-shell-mvp correction-pass review

You are reviewing a comprehensive correction pass to the `agent-shell-mvp`
design corpus. The pass:

1. Restructured flat `design/*.md` into a hierarchical tree under
   `$MERIDIAN_WORK_DIR/design/`.
2. Applied decisions D21–D28 from
   `$MERIDIAN_WORK_DIR/decisions.md` across the corpus.
3. Published wire contracts at every seam per D28.
4. Disposed of p1138 prior-review findings (H1, H2, M1–M5, L1–L6).

The architect spawn was p1153 (gpt-5.4). Its report is at
`/home/jimyao/gitrepos/meridian-channel/.meridian/spawns/p1153/report.md`.

## Your focus

Primary: **design alignment with D21–D28 + progressive-disclosure structure**.
Secondary: **wire-contract consistency** across seams.

Check specifically:

1. **D21 propagation**: No stale "shell is the product" framing. BYO-Claude
   local-only posture is consistent.
2. **D22/D23 propagation**: Mars moat + funnel framing is in strategy AND
   referenced by subsystem overviews (frontend, extensions, packaging).
3. **D25 propagation**: Frontend has ZERO biomedical references. Only 3–5
   core renderers. PyVista is an external example, never shell-internal.
4. **D26 propagation**: Extensions are composite (frontend + MCP) pairs with
   bidirectional flow via relay. The relay protocol has a VERSION field and
   envelope shape.
5. **D27 propagation**: Mars ItemKind is open/extensible; no hardcoded kind
   lists. CLI plugins and harness adapters are documented as V2+ extension
   points.
6. **D28 propagation**: Every seam has a "Wire Contract" section with
   VERSION field. Every V0 choice is defensible against both the focus test
   and the trap test.

Progressive disclosure check:

- Can a reader stop at `design/overview.md` and understand the whole MVP
  without drilling down? Flag anything that forces drill-down.
- Can a reader stop at each folder's `overview.md` and understand the
  subsystem without reading leaf docs? Flag violations.
- Do leaf docs re-explain parent context (bad) or orient with a one-line
  link up (good)?
- Are overviews linked down to children and children linked up?

Wire-contract consistency check:

- Is the normalized event schema (D1) referenced consistently in
  `events/normalized-schema.md`, `harness/abstraction.md`,
  `harness/adapters.md`, and `events/flow.md` with the same field names?
- Does the content-block wire format in `frontend/protocol.md` match what
  the backend claims it emits in `events/flow.md`?
- Does the interaction-layer relay protocol in
  `extensions/relay-protocol.md` match what the frontend and backend
  references say?

Prior-finding disposition check (from p1138):

- H1 — mid-turn-steering.md must contain the Phase 1.5 verification spike
  requirement and the `queue` → `none` fallback rule.
- H2 — execution/local-model.md + harness/adapters.md must explicitly note
  that the persistent-kernel issue is moot because the shell ships no
  kernel.
- M1 — frontend/protocol.md must use `{messageId, content, turnHints}`.
- M2 — events/normalized-schema.md must resolve the attachment carrier
  rule.
- M3 — no `--agents` references anywhere; only `--append-system-prompt` +
  `--mcp-config`.
- M5 — single-tab rule must be documented in events/flow.md.

## Files to read

Walk the new tree under `$MERIDIAN_WORK_DIR/design/`:

- overview.md
- strategy/{overview,funnel-and-moat}.md
- harness/{overview,abstraction,adapters,mid-turn-steering}.md
- events/{overview,normalized-schema,flow}.md
- frontend/{overview,chat-ui,content-blocks,protocol}.md
- extensions/{overview,interaction-layer,relay-protocol,package-contract}.md
- execution/{overview,local-model,project-layout}.md
- packaging/{overview,agent-loading}.md

Plus: `decisions.md` (D21–D28), architect report at
`.meridian/spawns/p1153/report.md`.

## Output

Standard reviewer report. Findings at High/Medium/Low severity. For each
finding: cite the doc + section, state the problem, recommend the fix.
Verdict: approve / approve-with-blocking-changes / reject. Keep the report
focused — the correction pass covered a lot of ground, prioritize the
highest-leverage issues.

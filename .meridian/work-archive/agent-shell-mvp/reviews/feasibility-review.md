**Shipability Verdict**

`NO.` The design has the right product direction, but V0 is not genuinely shippable yet for Dad to run the real μCT pipeline on real data without fighting the tool.

**Findings**

- High: The install story is much heavier than the docs admit. [local-execution.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/local-execution.md#L126) says quickstart is just Python and `uv`, but [repository-layout.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/repository-layout.md#L338) and [repository-layout.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/repository-layout.md#L366) also require `pnpm`, a frontend build, biomedical extras, and `mars sync`. The design does not budget for Claude Code installation/auth at all. That does not meet the bar in [requirements.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/requirements.md#L35) that Dad should not need the terminal.

- High: The landmarking path contradicts itself in the two most important docs. [interactive-tool-protocol.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/interactive-tool-protocol.md#L55) rejects in-kernel PyVista and chooses a backend-spawned subprocess at [interactive-tool-protocol.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/interactive-tool-protocol.md#L316). But [local-execution.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/local-execution.md#L667) reverses that and recommends an in-kernel blocking call. Step 6 is the hardest part of the workflow; V0 cannot be called shippable while Path B has two incompatible implementations.

- High: The biomedical agent is underspecified for autonomous real-data work. The profile in [agent-loading.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/agent-loading.md#L377) is a thin persona plus one skill reference, and the pipeline grounding still ends with a placeholder at [agent-loading.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/agent-loading.md#L422). For real threshold-watershed segmentation, landmark definitions, QC, and stats conventions, this is not enough unless the missing `biomedical-analyst` skill is much larger and more prescriptive than the design currently shows.

- Medium: The runtime/bootstrap story is internally inconsistent. [local-execution.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/local-execution.md#L60) chooses one global analysis venv, but [repository-layout.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/repository-layout.md#L322) and [repository-layout.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/repository-layout.md#L366) frame install as project-level `uv sync --extra biomedical`. Dad cannot debug which environment actually owns SimpleITK, VTK, and the kernel.

- Medium: Safety behavior is inconsistent. The sample profile sets `approval: confirm` in [agent-loading.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/agent-loading.md#L389), but [event-flow.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/event-flow.md#L752) says V0 launches Claude with bypassed permissions. The user-visible policy and runtime policy diverge.

- Medium: The first automated shell smoke is deferred to V1 in [repository-layout.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/repository-layout.md#L411). For a brand-new CLI subcommand, backend, WebSocket bridge, frontend import, persistent kernel, and interactive tool path, manual-only verification is too weak.

**Critical Path Risks**

1. Interactive landmark correction is not validated on the actual path Dad will need when auto landmarking fails.
2. `jupyter_client` + `ipykernel` + VTK/PyVista stability over 30-minute sessions is assumed, not proven.
3. Claude Code stream-json behavior is still partly reverse-engineered, and the currently installed CLI here does not even expose `meridian shell`.
4. The browser mesh viewer is passive-only in [frontend-integration.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/frontend-integration.md#L438), so PyVista remains mandatory rather than optional.
5. The biomedical prompt/skill package is not concrete enough yet to trust on real data.

**V0 Scope Cuts I’d Make**

- Cut mid-turn injection from V0.
- Cut session persistence beyond same-process reconnect.
- Cut user-facing opencode/model-switching surface.
- Cut the full drafting editor; chat output plus saved markdown is enough for the first results paragraph.
- Keep the local workdir ingest cut from [local-execution.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/local-execution.md#L522). That simplification is correct.

**V0 Scope Additions I’d Make**

- Add one bootstrap command that verifies `uv`, biomedical deps, `pnpm`, Claude Code binary/auth, `mars sync`, and desktop display support before first launch.
- Add a golden-dataset smoke that reaches DICOM load, segmentation, mesh display, and one landmark-picking correction.
- Add explicit DICOM folder validation and progress/error messaging before the agent starts work.
- Add a deterministic fallback playbook: if landmark auto-detection confidence is low, force `pick_points_on_mesh` with concrete labels and expected point count.
- Add a much larger biomedical skill corpus or a rigid per-step pipeline playbook.

**Install Burden Analysis**

The realistic prerequisite set is Python 3.12+, `uv`, a project venv, a separate analysis venv or biomedical extra, Node/pnpm, a built frontend, Claude Code installed and authenticated, `mars sync` for the biomedical pack, and a working local display stack for PyVista/VTK. That is too much for Dad as a manual setup. V0 needs either a real bootstrap installer or a prebuilt distribution that removes most of those decisions from the user path.

**Per-doc Findings**

- [overview.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/overview.md): right product direction, but it reads more implementation-ready than the repo actually is.
- [harness-abstraction.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/harness-abstraction.md): solid abstraction shape, but Claude V0 still leans on reverse-engineered behavior.
- [event-flow.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/event-flow.md): coherent in isolation, but assumes unproven transport and approval semantics.
- [frontend-protocol.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/frontend-protocol.md) and [frontend-integration.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/frontend-integration.md): good reuse of existing reducer/client work; cost is that Node/pnpm/Vite become part of Dad’s launch path.
- [agent-loading.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/agent-loading.md): weakest shipability doc because most biomedical competence is deferred to an unspecified skill.
- [interactive-tool-protocol.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/interactive-tool-protocol.md): stronger answer for Path B; keep the subprocess design.
- [local-execution.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/local-execution.md): good call on dropping the old upload pipeline, bad call on pulling PyVista back into the kernel.
- [repository-layout.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/design/repository-layout.md): packaging plan is coherent, but it understates how much product work `meridian shell start` really represents.

**Time-to-first-demo Estimate**

Best case: roughly 8 to 12 weeks before Dad can try a real-data workflow without constant developer supervision. A thinner canned-data demo could happen in 4 to 6 weeks, but that still would not clear the “Dad can run the actual pipeline” bar.

`meridian report create --stdin` failed because this installed CLI has no top-level `report` command, and the workspace is read-only, so I could not write [feasibility-review.md](/home/jimyao/gitrepos/meridian-channel/.meridian/work/agent-shell-mvp/reviews/feasibility-review.md).
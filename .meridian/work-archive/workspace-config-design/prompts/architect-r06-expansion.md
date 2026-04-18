# Architect Task — Expand R06 + close review gaps

## Context

Final design sweep for `workspace-config-design` before handoff to planning. Two reviewers (p1882 gpt-5.4, p1883 opus) surfaced findings; the user has decided on direction. This is the cleanup + targeted expansion pass.

Read these first:
- `.meridian/spawns/p1882/report.md` — gpt's adversarial review (1 blocker, 2 majors, 1 minor)
- `.meridian/spawns/p1883/report.md` — opus's consistency sweep (2 majors, 5 minors, 3 nits)

Design package lives under `.meridian/work/workspace-config-design/`. Full spec under `design/spec/`, architecture under `design/architecture/`, refactors in `design/refactors.md`, decisions in `decisions.md`.

## User directive (this is not negotiable)

**R06 stays as a prereq to R05.** The future-tax framing is accepted — the two launch pipelines must be unified before workspace projection lands, otherwise workspace becomes the 5th duplicated feature and every subsequent launch-touching feature pays a 2× cost.

But gpt is right that R06 as currently scoped **does not actually close the drift surface**. The user's directive: *make it impossible to drift*. That means R06 has to grow to cover the holes gpt identified, not stay narrow.

## Primary task — expand R06 + update D17

### R06 scope additions

Current R06 (`design/refactors.md:123-139`) touches only `launch/` files. Expand to include:

1. **`src/meridian/lib/ops/spawn/prepare.py:202, 323`** — spawn-side policy/permission/`SpawnParams` resolution. Must migrate into the shared seam so primary and spawn stop resolving policies in parallel code paths.
2. **`src/meridian/lib/launch/process.py:68`** — primary path rebuilds `run_params` after planning. Must consume the unified `LaunchContext` output instead of rebuilding.
3. **`src/meridian/lib/launch/plan.py:259` + `src/meridian/lib/launch/command.py:53`** — `MERIDIAN_HARNESS_COMMAND` bypass. D17 already says "explicit mode switch inside the shared seam"; this has to be enforced by R06 scope, not left implicit.
4. **Unify `RuntimeContext`** — the two types at `src/meridian/lib/launch/context.py:41` and `src/meridian/lib/core/context.py:13` collapse to one. This is already in the current R06 exit criteria but needs to be treated as a first-class scope item, not a byproduct.

### R06 exit criteria rewrite

After R06, the following invariants hold — enforce them in exit criteria text:

- **Exactly one composition function** consumed by both primary and spawn executors. Name it explicitly (`prepare_launch_context` or successor).
- **Exactly one `LaunchContext` type.**
- **Exactly one `RuntimeContext` type.**
- **Exactly one workspace-projection insertion point** — R05 must have a unique seam to target.
- **Exactly one env-build path** — no parallel `build_launch_env` / `build_harness_child_env` duplications across pipelines.
- **Exactly one policy/permission/SpawnParams resolution site** — `ops/spawn/prepare.py` either collapses into the shared seam or becomes a thin caller of it.
- **`MERIDIAN_HARNESS_COMMAND`** is an explicit branch inside the shared seam, not a parallel composition path.

Also add the test-file blast radius per opus F10: `rg -l "RuntimeContext|prepare_launch_context|LaunchContext|build_launch_env|build_harness_child_env" tests/` and list results in R06 scope.

### D17 update

Rewrite `decisions.md` D17 section to:

1. Keep the Depth-1 directive (unify seams) but **respond directly to gpt's rebuttal** — the p1878 probe's Depth-2 recommendation is rejected because it leaves drift surface that the workspace feature immediately extends. Name the drift surface: 5 duplicated features before workspace, 6 after, with the 5th being the feature we're actively shipping. Cite that drift compounds and the seam debt is paid either way; paying it now keeps R05 targeting a single point.
2. Expand "Preserved divergences" and "Out of scope" sections to reflect the widened R06 scope above. What was "out of scope" before (fork materialization, session-ID extraction, PTY execvpe) stays out, but `ops/spawn/prepare.py` + `MERIDIAN_HARNESS_COMMAND` bypass + `RuntimeContext` dedup move from "out of scope / risks acknowledged" into **in-scope for R06**.
3. Add one paragraph on the drift invariant: after R06, the codebase must have exactly one of each composition artifact. This is the "impossible to drift" lever — future features touch one seam or none.

## Secondary task — close the MAJOR relative `MERIDIAN_WORKSPACE` spec gap

Both reviewers flagged WS-1.u2 (`design/spec/workspace-file.md:17`) as a real spec hole: behavior is undefined when `MERIDIAN_WORKSPACE` holds a *relative* path. D12 says v1 is absolute-only but doesn't pin fallthrough semantics.

Pin one behavior. Recommended (unless you find better): **treat a relative value as an invalid override, emit a per-invocation advisory, and fall through to default discovery.** Rationale: matches D13 (missing override target → `absent` + advisory) style; hard-error would block launches on a typo; silent fallthrough loses the signal.

Encode it as:
- a new EARS statement under WS-1 (e.g. `WS-1.e5`) OR an expansion of `WS-1.u2` with an explicit non-absolute clause
- surfacing path in `design/spec/surfacing.md` (new SURF-1 EARS or fold into e6)
- reflect in `design/architecture/paths-layer.md` discovery rules
- record in `decisions.md` as `D18 — Relative MERIDIAN_WORKSPACE behavior` with the two rejected alternatives (hard error, silent fallthrough)

## Tertiary task — convergence cleanup

These are doc nits. Fix in one pass:

- **SURF-1.e3 gap** (`design/spec/surfacing.md`): decide between renumbering e4–e6 → e3–e5, or adding a `### SURF-1.e3 — (deleted)` tombstone. Tombstone is usually safer because downstream references (if any) don't silently re-bind.
- **surfacing.md `Realized by`** (line 8): add `../architecture/workspace-model.md` since A03 already claims to realize SURF-1.e1/e2.
- **D6** (`decisions.md:251-256`): update R04 reference to R01 (R04 is folded).
- **R02 exit criteria** (`design/refactors.md:46`): rewrite "No command reads from root while another writes to legacy" to target-state wording, e.g., "All reads and writes target `meridian.toml` through the shared `ProjectConfigState`; no command resolves project config from a different location."
- **WS-1.e2** (`design/spec/workspace-file.md:32-33`): clarify that `--from mars.toml` emits *commented* TOML entries, per D14. Current text reads like active `enabled = false` entries.
- **decisions.md "How this file is used"** (line 455): update "D1–D7" scope to "D1–D18" (or whatever the final count is after adding D18 for relative `MERIDIAN_WORKSPACE`).
- **feasibility.md OQ-2** (line 131-132): reformat the garbled `Low **Status:** deferred. priority;` text.
- **CTX-1 non-requirement edge case**: add a one-liner noting `MERIDIAN_HARNESS_COMMAND` bypass is an instance of `CTX-1.w2`, realized as `unsupported:harness_command_bypass` in the architecture layer.

## Do NOT touch

- R01, R02, R05 scope — unchanged.
- Feature-level spec (CFG-1, WS-1, CTX-1, SURF-1, BOOT-1) substance — only the specific cleanups above.
- D8 (no migration) — keep.
- D12 (absolute-only v1) — keep; D18 pins the previously-unspecified fallthrough.
- R03 — stays conditional.

## Deliverable

Edit the design files in place. Produce a final "what changed" summary in your report so the next reviewer knows what to diff. Do not commit — the user will review first.

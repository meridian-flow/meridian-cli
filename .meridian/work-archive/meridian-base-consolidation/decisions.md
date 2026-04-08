# Decision Log — meridian-base Skills Consolidation

## D1 — Skill name: `__meridian-cli`, not `__meridian`

**Decision:** Name the new singular CLI reference skill `__meridian-cli`.

**Why:** The user explicitly asked for `__meridian-cli` in the spawning prompt. Beyond user preference, the name makes the scope unambiguous: this skill teaches the CLI surface and the principles behind it. Reserving `__meridian` (without the suffix) leaves room for a future skill that teaches meridian's broader runtime model — e.g., the harness adapter abstraction, the spawn lifecycle state machine, the JSONL event schema — at a different altitude. Conflating "the CLI" with "meridian as a system" would force one skill to do two altitudes badly.

**Rejected:** `__meridian` (the issue's original name) — ambiguous in a way that would re-emerge later.

## D2 — Split `__meridian-session-context` rather than fold-and-leak

**Decision:** Delete `__meridian-session-context` from base. Move CLI-reference content into `__meridian-cli`. Move workflow content into a new dev-workflow skill.

**Why:** The skill currently does two unrelated jobs. Folding the whole thing into `__meridian-cli` keeps the cross-layer leak — `__meridian-cli` would inherit `@explorer` references. Leaving it in base unchanged keeps the leak too. Splitting honors the layer boundary and lets each half live where its assumptions are valid.

**Rejected:**
- *Fold whole thing into `__meridian-cli`.* Leaks `@explorer` into base.
- *Leave it in base, drop the `@explorer` references.* The workflow guidance becomes vague — "delegate to a cheap exploration spawn" is true but loses the concreteness that makes it actionable. The pattern is real workflow knowledge and deserves a real home.
- *Move whole thing to dev-workflow.* Then base loses the CLI reference for `meridian session ...`, forcing every base-level user to learn it ad-hoc from `--help`. That's actually fine for a sufficiently rich `--help`, but the consolidation is more legible if `__meridian-cli` covers the whole CLI surface uniformly.

## D3 — New dev-workflow skill name: locked as `session-mining` (revised after review)

**Decision (revised):** Lock the name as `session-mining` now, in this design. Do not defer to the planner.

**Why revised:** Reviewer p1065 flagged that half-deferring naming creates a real coordination risk: doc `06-consumer-profile-updates.md` already uses `session-mining` as if it were the real name. If the planner picks something different, every consumer profile reference has to be updated separately, and the risk of inconsistent rename across files is high. Either commit now or block phase 1 on naming. Committing now is cheaper and lower-risk.

**Original rationale (still valid):** `session-mining` describes what the skill is *for*, not what command it wraps. Alternatives `session-context` (too close to the deleted base skill — confusing), `transcript-mining` (correct but jargon-flavored), and `context-recovery` (broader than the actual skill) lose to it.

**Why:** Naming this well requires balancing several constraints — it's not "session reading" (too narrow), not "context recovery" (too broad), not "transcript mining" (right shape but odd phrasing). `session-mining` captures the workflow it teaches without locking the planner out of a better choice. Nothing in the design depends on the specific name beyond consistency, so deferring is cheap.

**Alternatives noted in passing:** `session-context` (too close to the deleted base skill — confusing), `transcript-mining` (correct but jargon-flavored), `context-recovery` (broader than the actual skill).

## D4 — Generic-guidance vs example reference policy

**Decision:** In base skills, dev-workflow agent names like `@reviewer` are allowed inside *examples* that illustrate a concept, but not inside *generic guidance* that prescribes behavior. The test: if you delete the agent name and the sentence still makes sense as a prescription, it was generic guidance — rewrite. If the sentence becomes meaningless, it was an example — keep.

**Why:** Examples lose their pedagogical value when stripped of concrete names. "An agent profile that scopes tools narrowly" is true but forgettable; "A `@reviewer` profile that scopes tools to `git diff` and `cat`" is memorable. The skill is still correct in a project without dev-workflow — the reader just doesn't have that specific profile to look at, but the concept transfers. Generic guidance is different: "fan out @reviewers" tells the reader to do something, and that something is broken without dev-workflow.

**Rejected:**
- *Forbid all dev-workflow agent names in base.* Strips legitimate examples and weakens `agent-creator` / `skill-creator`.
- *Allow them everywhere.* Lets generic guidance leak silently.

This policy gets codified as a paragraph in both `agent-creator/anti-patterns.md` and `skill-creator/anti-patterns.md` so the next sweep knows the rule.

## D5 — `--help` text fixes are prerequisite, not concurrent

**Decision:** The plan executes `--help` expansions *before* deleting the old skills.

**Why:** The new `__meridian-cli` skill points agents at `--help` as the canonical reference. If an agent loads the new skill while the help text is still thin, it lands on inadequate content and either fails or fabricates. Doing help-text expansion first means the consolidation never has a window where references are broken.

**Rejected:** *Concurrent* — the old skills cover the gaps so it doesn't matter what order things land. Wrong: the old skills go away in the same plan, and there's no guarantee the plan executes phases atomically across an interrupted session. Sequencing is cheap insurance.

## D6 — Slim `--help`-duplicating content, don't gut it

**Decision:** Sections in `__meridian-cli` that touch a CLI surface use a one-paragraph overview + a single `--help` pointer. They do *not* enumerate flags, even where the old skill did. Exception: tables that capture *patterns* (failure-mode → first move, env-var → purpose) stay because `--help` doesn't teach those.

**Why:** The point of consolidation is fewer lines, not the same lines redistributed. Re-documenting flags here defeats the purpose and creates the same drift problem we're solving. The failure-mode table in particular survives because reading "exit code 137 means SIGKILL, check OOM" is faster than reading the spawn show JSON and inferring it.

**Rejected:**
- *Drop the failure-mode table too.* Loses the only durable content from `__meridian-diagnostics`. Agents need this when state goes weird, and reading it from `meridian doctor --help` would require the doctor help to grow into a troubleshooting guide — wrong altitude for `--help`.
- *Keep the full flag tables, just consolidated into one file.* Same drift, same line count, no benefit.

## D7 — Skip a separate planner; the design is small enough for impl-orchestrator directly

**Decision (recommendation, not forcing):** Recommend that the dev-orchestrator skip spawning a dedicated planner and hand this design straight to impl-orchestrator with a brief phase outline embedded in the handoff.

**Why:** The work decomposes cleanly into three obvious phases:

1. **Expand `--help` text** (`04-cli-help-gaps.md` is the spec). Verification = run each updated `--help`.
2. **Create `__meridian-cli` and the new dev-workflow skill; delete the three old base skills; update consumer profiles; fix the orchestrator-line-29 leak; codify the example-vs-generic policy in anti-patterns docs.** Verification = `meridian mars sync` clean + grep for stale refs returns empty.
3. **README updates and final smoke check.** Verification = manual review.

There are no parallelization questions, no design uncertainties left unresolved, and no risky-but-reversible decisions that benefit from a planner's deeper decomposition. A planner would re-derive the same three phases.

**If the dev-orchestrator disagrees** (e.g., they want a planner to lock the new skill name in phase 1, or to surface help-text edits I missed), spawning one is cheap and harmless. The decision is "default to skipping; spawn one if it adds value." Logged here so future review can second-guess if needed.

## D8 — No new `resources/` tree, with one possible exception for the mars TOML schema

**Decision:** The new dev-workflow `session-mining` skill ships as a single SKILL.md, no resources/. Same for `__meridian-cli`, with one *possible* exception below.

**Why:** Both skills are deliberately small. A `resources/` tree would invite the kind of depth that re-introduces the duplication we're cutting. If a future need pushes one of them past ~200 lines, that's the moment to revisit — not now.

**Rejected:** Pre-creating `resources/architecture-overview.md` for `__meridian-cli`. Tempting because the runtime model is genuinely worth a longer doc, but it's a different skill (the eventual `__meridian` that D1 reserves the name for). Don't hide it under `__meridian-cli/resources/`.

**Possible exception — mars-toml-reference.md:** The deleted `__mars/` skill linked to `resources/mars-toml-reference.md` containing the full `mars.toml` schema. Reviewer p1066 flagged that without explicit handling, the schema reference vanishes. `04-cli-help-gaps.md` Gap 8 enumerates three resolution options. The preferred option is for mars to render the schema via `--help` (option 1). If that's not viable in the consolidation timeframe, **this decision is amended to allow exactly one resource file at `__meridian-cli/resources/mars-toml-reference.md`** as a one-off exception. The exception does not generalize — every other piece of content stays in the SKILL body or out.

## D9 — Trim duplicated principles from `__meridian-spawn` after `__meridian-cli` lands

**Decision:** `__meridian-cli` is canonical for the principles in its §3 (JSON discipline, auto-recovery, env vars). `__meridian-spawn` trims its restatements (lines 14, 97, 117–118 in the current file) to one-line cross-references and relies on co-loading.

**Why:** Reviewer p1066 identified that the new skill duplicates content already in `__meridian-spawn`. Without an explicit decision the duplication just happens silently and re-introduces the drift problem the consolidation is trying to solve. Canonicalizing in the smaller, principle-focused skill is the right altitude.

**Safety condition:** before deleting any duplicated lines from `__meridian-spawn`, the implementer verifies that no profile loads `__meridian-spawn` without also loading `__meridian-cli`. The consumer-profile rule in `06` makes that true after the consolidation lands, but the verification step is mandatory because a missed profile would silently lose the principle content.

**Rejected:**
- *Accept the duplication.* Re-introduces drift, defeats the consolidation.
- *Canonicalize in `__meridian-spawn` and trim `__meridian-cli`.* Wrong altitude — `__meridian-spawn` is about delegation, not CLI principles, and not every consumer of CLI principles is a delegator.

## D10 — Apply the "what changes" rule to the consumer-profile sweep, don't punt

**Decision (revised after review):** `06-consumer-profile-updates.md` provides an explicit rule for `__meridian-cli` adoption (every profile whose body invokes a CLI command beyond `meridian spawn` / `meridian work` gets the skill). The implementer applies the rule by grepping; the planner does not need to enumerate every profile by hand.

**Why:** Reviewer p1065 flagged that the original "sweep and decide per profile" handed implementation-meaningful judgment to the implementer with no guidance. A rule lets the implementer apply the judgment mechanically and gives the verifier a grep target. This trades "design enumerates each profile" for "design provides a rule + verification check," which is the right altitude for a consolidation that touches a moving set of agent profiles.

## D11 — Add `__meridian-cli` to base `__meridian-orchestrator` (deviation from 06 Rule 3)

**Decision:** Added `__meridian-cli` to the skills array of `meridian-base/agents/__meridian-orchestrator.md`, contrary to `design/06-consumer-profile-updates.md` Rule 3 which said the base orchestrator should stay minimal and skip `__meridian-cli`.

**Why:** D9's safety condition mandates that every profile loading `__meridian-spawn` must also load `__meridian-cli` before the duplicated principle lines (env vars, JSON discipline, auto-recovery) are trimmed from `__meridian-spawn`. The base `__meridian-orchestrator` loads `__meridian-spawn`. The two design decisions (06 Rule 3 vs D9 safety) collide: either `__meridian-spawn` cannot be trimmed for that profile, or `__meridian-cli` must be added. Adding `__meridian-cli` is the cheaper resolution — it costs one extra skill load on the base orchestrator, but preserves the principle-canonicalization in `__meridian-cli` for every consumer of `__meridian-spawn`.

**Rejected:**
- *Skip the `__meridian-spawn` trims entirely.* Defeats D9 and leaves the duplication.
- *Trim `__meridian-spawn` but leave base orchestrator without `__meridian-cli`.* Silently loses principle content for the most foundational orchestrator.
- *Make `__meridian-cli` optional via conditional load.* No such mechanism exists.

**What changed:** `meridian-base/agents/__meridian-orchestrator.md` skills now include `__meridian-cli` with `__meridian-spawn`, `__meridian-work-coordination`, and `__meridian-privilege-escalation`. The same treatment was applied to `tech-writer` and `impl-orchestrator` for the same D9 safety reason.

## D12 — Drop `__` prefix from base meridian profiles and skills

**Decision:** Rename base meridian-prefixed profiles and skills to drop the double-underscore prefix: `__meridian-spawn`, `__meridian-work-coordination`, `__meridian-cli`, `__meridian-privilege-escalation`, `__meridian-orchestrator`, and `__meridian-subagent` become `meridian-*` names.

**Why:** The `meridian-` stem already provides clear namespace identity. Keeping both `__` and `meridian-` is redundant and adds noise in profile references, docs, and commands. Applying the rename consistently (including `__meridian-subagent`) avoids mixed naming conventions in the same package and reduces migration churn later.

**Rejected:**
- *Rename only `__meridian-orchestrator` and leave `__meridian-subagent`.* Inconsistent naming inside the same base profile set.
- *Keep `__` for "internal" skills only.* Adds a second naming rule with little practical value and more cognitive overhead.

## D13 — Keep spawn skill pointers to moved CLI resources (repoint, don't drop)

**Decision:** In `meridian-base/skills/meridian-spawn/SKILL.md`, keep explicit pointers for troubleshooting and configuration, but repoint them to `../meridian-cli/resources/debugging.md` and `../meridian-cli/resources/configuration.md` after relocation.

**Why:** The references are still useful at point-of-need in the spawn workflow. Repointing preserves discoverability while keeping ownership of those docs at the CLI layer.

**Rejected:** Dropping the pointers entirely and relying only on co-loaded `meridian-cli` to surface those docs.

## D14 — Also rename `__meridian-subagent` → `meridian-subagent` (Phase 4 scope expansion)

**Context:** Phase 4 scope as handed to the coder explicitly excluded `__meridian-subagent` from the rename, listing only the four `__meridian-*` skills plus `__meridian-orchestrator` for the prefix drop. The Phase 4 coder (p1089) expanded scope and renamed `__meridian-subagent` → `meridian-subagent` anyway, propagating through Python defaults (`settings.py`, `ops/config.py`, `ops/diag.py`, `ops/spawn/prepare.py`) and `docs/configuration.md`. A follow-up fix pass (p1094) updated the four test fixture files that were still using the old string so everything is self-consistent.

**Decision:** Accept the expansion. `__meridian-subagent` becomes `meridian-subagent`.

**Why:** The stated rationale for Phase 4 was "drop the `__` prefix everywhere" — the redundant prefix conflicts with the `meridian-*` stem that already signals the layer. Keeping `__meridian-subagent` while every other base skill/agent drops the prefix would recreate the exact inconsistency the phase was supposed to fix (especially visible because `meridian-default-orchestrator` and `meridian-subagent` are listed together as the two base-agent defaults in `settings.py`). The exclusion in the original phase scope was an oversight by the impl-orchestrator, not a deliberate carve-out.

**Rejected:** Reverting the subagent rename to match the original phase scope. Would leave the base agent directory mixed (`meridian-default-orchestrator.md` alongside `__meridian-subagent.md`) and the Python defaults split across naming conventions.

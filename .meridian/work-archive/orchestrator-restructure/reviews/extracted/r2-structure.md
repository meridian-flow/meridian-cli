## Review: orchestrator-restructure design v2 — structural emphasis sanity

Verdict: **request changes**. v2’s framing is materially stronger than v1, but there are still “rhetorical strength without operational teeth” gaps that can let the same tangled-target failure slip through again.

### CRITICAL

- **Where:** `.meridian/work/orchestrator-restructure/design/planner.md:59` + `.meridian/work/orchestrator-restructure/design/impl-orchestrator.md:39` + `.meridian/work/orchestrator-restructure/design/dev-orchestrator.md:29`  
  **What:** The planner is explicitly told to surface “cannot decompose for parallelism” and flag it back to impl-orch, but neither impl-orch nor dev-orch has any specified behavior that treats that signal as structurally blocking. Impl-orch only respawns planner for completeness/consistency issues, not “design preserved coupling” issues.  
  **Why it matters:** This is exactly the failure path you’re trying to prevent: a structurally tangled design “converges”, the planner produces a sequential plan, dev-orch can approve it as “the plan is obvious / fine”, and the structural wrongness surfaces only during implementation (again).  
  **Suggested fix:** Make “planner reports structural non-decomposability” an explicit **pre-execution structural gate**:
  - Require `plan/overview.md` to include a **Parallelism Posture** field (e.g. `parallel | limited | sequential`) plus **cause classification** (`inherent constraint` vs `structural coupling preserved by design`).  
  - In `.meridian/work/orchestrator-restructure/design/impl-orchestrator.md`, specify: if posture is `sequential` due to `structural coupling`, impl-orch must **stop before execution** and trigger a redesign decision (either a redesign brief variant or a “structural escalation to dev-orch” report).  
  - In `.meridian/work/orchestrator-restructure/design/dev-orchestrator.md`, specify: dev-orch must treat that condition as **blocking** unless the user explicitly accepts the sequential tradeoff.

### HIGH

- **Where:** `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:16`, `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:47`, `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:57`, `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:91`, `.meridian/work/orchestrator-restructure/design/overview.md:95`, `.meridian/work/orchestrator-restructure/decisions.md:130`  
  **What:** The structural reviewer is described as “by default” in multiple places, and also as “mandatory”, and also as “not a separate mandatory pass.” This creates a loophole where a real design-orch instance can rationalize skipping it on “small” designs, or treat it as optional hygiene.  
  **Why it matters:** The whole point of v2 is that this *cannot* be left to taste/judgment; “small” designs are precisely where early coupling decisions lock in. Ambiguous mandate language reintroduces the skip path.  
  **Suggested fix:** Normalize the language everywhere to: **required reviewer inside the standard fan-out (no separate phase), never skipped**. Concretely:
  - Replace “by default” with “**required**” when referring to the structural reviewer.  
  - Replace “not a separate mandatory pass” with “**not a separate phase gate; still required in the fan-out**” to remove the accidental negation vibe.  
  - Add an explicit convergence rule: design-orch **may not declare convergence** unless it can cite the structural reviewer’s PASS (or the explicit decision that overrides PASS).

- **Where:** `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:33` + `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:45` + `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:59`  
  **What:** “Fix or preserve” + “planner should be able to see decomposition” is a good question, but the design doesn’t require evidence strong enough to prevent “sounds plausible” answers.  
  **Why it matters:** The original failure mode was a design that *felt* coherent and review-converged while landing a tangled target. Vibes-based “fixes coupling” prose can still pass.  
  **Suggested fix:** Add minimal, concrete evidence requirements to the Terrain section contract (keep it lightweight, but force specificity), e.g.:
  - `fix_or_preserve: fixes | preserves | unknown` (and `unknown` blocks convergence).  
  - Structural delta must list **specific cuts** with named modules/interfaces (not just generic “extract interface Y”), and include at least one **“parallel clusters after prep” hypothesis** (even if later corrected by runtime constraints).

### MEDIUM

- **Where:** `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:49`  
  **What:** The structural reviewer brief is directionally right but still underspecified for actionable output: it tells the reviewer what to look for, but not what to *produce* (no required artifact shape; no forced decomposition attempt).  
  **Why it matters:** A structural reviewer can still return vague “modularity could be improved” feedback that doesn’t bite, and the convergence loop can still drift to “LGTM”.  
  **Suggested fix:** Require the structural reviewer to produce a “decomposability sketch”:
  - Name 1–2 cross-cutting prep cuts and at least 2 candidate parallel clusters *or* explicitly state “cannot find clusters” and block.  
  - Explicitly call out 3–5 anti-pattern signals to check (shared global state, wide interface touched by multiple clusters, import cycle risk, “god module”, cross-layer dependencies). This can stay in the reviewer prompt/body without turning into a huge SOLID lecture.

- **Where:** `.meridian/work/orchestrator-restructure/design/overview.md:91` + `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:26`  
  **What:** The docs repeatedly reference “Terrain section at end of `design/overview.md`”, but the package doesn’t provide a concrete template (it’s only described indirectly).  
  **Why it matters:** Without a template, the Terrain section becomes stylistic and drifts across runs, which weakens enforceability and reviewability.  
  **Suggested fix:** Add a minimal Terrain template block (even as a copy/paste skeleton) in the design-orch doc or overview, with the required fields and the evidence expectations above.

### LOW (SOLID framing)

- **Where:** `.meridian/work/orchestrator-restructure/design/design-orchestrator.md:30` + `.meridian/work/orchestrator-restructure/design/overview.md:87`  
  **What:** SOLID is mentioned, but not operationalized; the language stays at “modularity/cohesion/boundaries.”  
  **Why it matters:** Probably fine, but the user explicitly named SOLID, and using a small subset (SRP/ISP/DIP) as reviewer vocabulary could improve consistency.  
  **Suggested fix:** Keep the broader terms, but add a short “SOLID-as-signals” mapping for the structural reviewer (no need to enforce SOLID dogma).

Note: I didn’t run `meridian spawn report create --stdin` because this session is in a read-only sandbox; this message is the full report content for fallback extraction/persistence.

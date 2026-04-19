# Biomed MVP Launch Prioritization

## Scope

Single planning document for the biomed MVP launch. This plan captures:

- what is actually launch-blocking
- what should be sequenced
- what can be explored or designed in parallel
- what should be deferred until after launch

The MVP target is not "Meridian as a CLI for developers." The target is:

- researchers on Windows
- primarily using a UI, not a terminal
- launching a packaged biomed agent/skill set
- with Claude as a strong design path but not the only viable runtime path
- with OpenCode as an important non-Anthropic lane, especially for Google models

## MVP Constraints

1. Researchers do not want to use the terminal directly.
2. Windows support is required for the actual user environment.
3. UI is required for the launch experience.
4. Harness provisioning is part of the product surface, not an implementation detail.
5. OpenCode parity matters because Anthropic reliability cannot be assumed.

## Parallelism Posture

**Posture:** mixed sequencing with parallel design lanes

**Cause:** the highest-priority implementation work shares low-level lifecycle and platform files, but several launch-shaping questions can still be researched and designed in parallel without merge risk.

## Repo Split

This launch plan crosses at least two repos.

### `meridian-cli`

Owns:

- Windows runtime support
- researcher UI / app architecture
- OpenCode harness parity
- harness provisioning and setup checks
- runtime observability
- spawn lineage and lifecycle correctness

### `mars-agents`

Owns:

- package/distribution mechanics for the biomed agent and skill set
- install/sync ergonomics for the shipped package
- packaging metadata and package update flows

Treat this as a **fully independent lane by default**. It lives in a different repo and should proceed in parallel unless it discovers a CLI contract change that must be reflected back into `meridian-cli`.

### Prompt / package source repos

Likely own:

- the actual biomed agent and skill definitions
- prompt/docs examples specific to the shipped biomed package

**Implication:** some launch work can and should proceed in parallel simply because it lives in different repos and does not share write scope.

## Priority Tiers

### Tier 1: Launch Blockers

These directly determine whether the biomed MVP can be shown to real researchers.

1. **Windows support**
   - Active work: `windows-cross-platform`, `windows-port-research`
   - Why: if the target environment is Windows, failure here invalidates the MVP regardless of agent quality.

2. **Researcher UI**
   - Active work: `app-session-architecture`
   - Why: researchers will not adopt a terminal-first experience. A minimal but credible UI is required.

3. **Harness provisioning / setup experience**
   - No single active work item cleanly owns this yet.
   - Why: packaging Meridian without packaging Claude Code / OpenCode setup produces a broken first-run experience.

4. **OpenCode parity**
   - Archived evidence: `opencode-gap-analysis`
   - Why: Meridian needs a credible non-Anthropic path. The known gaps are session capture, continue, fork, report extraction, model fidelity, and effort mapping.

5. **Biomed package distribution**
   - Active work: `mars-capability-packaging`
   - Why: the MVP must install/sync the agent and skill set cleanly.

### Tier 2: Supporting Reliability Work

These are important because they directly affect launch confidence and diagnosis.

1. **Observability**
   - Active work: `observability`
   - Why: crash diagnostics and runner logs are needed to debug launch failures quickly.

2. **Spawn parent tracking**
   - Active work: `spawn-parent-tracking-bug`
   - Why: nested lineage errors make orchestration and diagnosis harder, especially during launch prep.

3. **Planner handoff reliability**
   - Active work: `planner-handoff-reliability`
   - Why: prompt truncation and wait-discipline failures can poison autonomous work loops.

4. **Work lifecycle trust bug**
   - Active work: `work-done-status-sync`
   - Why: small, but it undermines trust in the dashboard and is cheap to fix.

### Tier 3: Lower Priority / Narrow Scope

1. **orchestrator-profile-hardening**
   - Keep only the configuration/prompt consistency parts that materially affect launch.
   - Do not treat it as the main fix for long-running child wait behavior.

2. **launch-fs-r06-docs**
   - Correctly blocked.
   - Not a launch blocker for the biomed MVP.

## Parallel Research / Design First

These should run first, and they are specifically good parallel work because they mostly produce clarity, not merge conflicts.

1. **Windows install and runtime research**
   - Active work: `windows-port-research`
   - Question: what must be true for a real Windows researcher machine?

2. **Researcher UI scope**
   - Active work: `app-session-architecture`
   - Question: what is the smallest UI that removes terminal dependency?

3. **OpenCode parity decomposition**
   - Re-open or recreate from archived `opencode-gap-analysis`
   - Question: which parity gaps are true launch blockers vs later polish?

4. **Harness provisioning / onboarding design**
   - Likely new work item
   - Question: how does the app detect, explain, and repair missing harness installs and auth?

5. **Biomed packaging / install design**
   - Likely partly in `mars-agents`
   - Question: how does the biomed package get installed, updated, and selected by non-terminal users?

6. **Biomed demo workflow definition**
   - Likely prompt/package repo plus launch docs
   - Question: which 2-3 workflows will prove the product value most clearly?

7. **Small workflow trust bug**
   - Active work: `work-done-status-sync`
   - Small enough to implement immediately while the larger design lanes run.

## Implementation Lanes That Can Probably Run At The Same Time

These are the coding lanes that look feasible to run concurrently without obvious file overlap, assuming the design/research round has already clarified the shape.

1. **UI / app lane**
   - Primary work: `app-session-architecture`
   - Expected files: `frontend/`, app endpoints, app session wiring
   - Low overlap with Windows portability internals and `mars-agents`.

2. **Packaging lane**
   - Primary work: `mars-capability-packaging`
   - Expected repo: partly or mostly `mars-agents`
   - Treat as fully parallel to `meridian-cli` runtime work unless a contract change is discovered.

3. **OpenCode parity lane**
   - Primary work: new/re-opened OpenCode parity work item
   - Expected files: `src/meridian/lib/harness/opencode.py`, `connections/opencode_http.py`, extractor/reporting paths, OpenCode smoke tests
   - Likely low overlap with app UI work and `mars-agents`.

4. **Provisioning / onboarding lane**
   - Primary work: new setup/onboarding work item
   - Expected files: app setup screens, detection logic, possibly docs and setup endpoints
   - Can likely run alongside packaging if responsibilities are split cleanly.

5. **Small dashboard trust fix lane**
   - Primary work: `work-done-status-sync`
   - Independent enough to proceed anytime.

## Recommended Sequence

### Round 1: parallel research/design

- `windows-port-research`
- `app-session-architecture`
- OpenCode parity decomposition
- harness provisioning / setup design
- biomed packaging / install design
- biomed demo workflow definition
- `work-done-status-sync`

**Reason:** this round discovers the launch shape while keeping implementation lanes from stepping on each other prematurely.

### Round 2: implementation lanes with low overlap

Sequence this round:

1. `windows-cross-platform`
2. harness provisioning / setup implementation
3. OpenCode parity implementation
4. `mars-capability-packaging`

**Reason:** Windows defines the runtime substrate. Packaging and OpenCode parity can proceed in parallel once their designs are clear, especially where `mars-agents` owns the packaging side.

### Round 3: UI integration and researcher workflow shaping

1. `app-session-architecture` implementation
2. biomed workflow onboarding in the UI
3. durable output / session revisit flows

**Reason:** once runtime support and harness setup are credible, the UI can expose them coherently instead of working around instability.

### Round 4: Reliability tightening for launch confidence

1. `observability`
2. `spawn-parent-tracking-bug`
3. `planner-handoff-reliability`

**Reason:** these should be applied where they most improve diagnosability and robustness without delaying the user-facing launch path unnecessarily.

## Work That Should Not Be Coded In Parallel

### Windows cross-platform and observability

These likely overlap in:

- `src/meridian/lib/launch/process.py`
- `src/meridian/lib/launch/signals.py`
- `src/meridian/lib/launch/runner.py`
- `src/meridian/lib/launch/streaming_runner.py`

**Guidance:** do not run them as fully independent coding lanes. Let Windows define the platform seams first, then implement observability on top of those seams.

### Spawn lineage and generic runner/lifecycle fixes

`spawn-parent-tracking-bug`, observability, and any deeper wait/reaper changes all risk touching related launch/runtime surfaces. Keep them coordinated rather than fan-out coded blindly.

## Immediate Recommendations

### Start / continue now

- `windows-port-research`
- `app-session-architecture`
- `mars-capability-packaging`
- `work-done-status-sync`
- create/revive OpenCode parity planning
- create harness provisioning / onboarding planning

### Re-open or create explicitly

1. **OpenCode parity**
   - revive from archived `opencode-gap-analysis`
   - break into:
     - session capture
     - continue semantics
     - fork semantics
     - report extraction
     - Google model fidelity
     - effort mapping
     - smoke/docs coverage

2. **Harness provisioning / onboarding**
   - create a work item if none exists
   - scope:
     - detect installed harnesses
     - detect auth/config state
     - surface setup guidance in the UI
     - define primary and fallback launch paths

### Delay for later rounds

- broad `orchestrator-profile-hardening`
- `launch-fs-r06-docs`
- generalized runtime cleanup not tied to Windows, UI, packaging, or OpenCode parity

## Primary and Fallback Launch Paths

### Primary path

- researcher uses UI on Windows
- biomed package is already installed/synced
- Claude-backed path available when stable

### Fallback path

- same UI and biomed package
- OpenCode-backed Google model path

**Why this matters:** the MVP should demonstrate Meridian surviving provider instability, not depending on a single provider being healthy on demo day.

## Minimum Launch Exit Criteria

1. A Windows researcher can install and open the app.
2. The app can tell whether Claude Code and OpenCode are installed/configured.
3. At least one primary and one fallback harness path are usable.
4. The packaged biomed agent/skill set is available without manual YAML editing.
5. A researcher can run at least one core biomed workflow through the UI without needing the terminal.
6. Failures are diagnosable enough that launch prep is not blind.

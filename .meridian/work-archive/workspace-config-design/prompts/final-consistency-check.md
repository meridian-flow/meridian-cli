# Final Consistency Check — Cross-document coherence

## Context

`workspace-config-design` has been through five architect passes and four review rounds. The latest rewrite (p1894) reframed R06 around 3 driving adapters through one factory. That change touched:

- `design/refactors.md` (R05 cross-refs + R06 full rewrite)
- `decisions.md` (D17 full rewrite)
- `design/architecture/harness-integration.md` (Launch composition section rewrite)

The rest of the design tree has been touched by prior passes (p1890 and earlier):
- `requirements.md`
- `design/spec/*.md` (config-location, workspace-file, surfacing, context-root-injection, boot)
- `design/architecture/*.md` (workspace-model, paths-layer, config-loader, surfacing-layer, harness-integration)
- `design/feasibility.md`
- `design/refactors.md` (R01-R05)
- `decisions.md` (D1-D18)

## Your task — consistency check, not adversarial review

You are the **cross-document coherence** reviewer. Your job is to find contradictions, stale references, vocabulary drift, and numerical mismatches between design documents. Not "is the architecture right?" but "does every document tell the same story about the architecture?"

Read the whole design tree. Work systematically, not by sampling.

### Specific checks

1. **Vocabulary consistency across documents**
   - The new framing uses: "driving adapter" (3 of them), "driving port" (1, the factory), "driven port" (1, adapter protocol), "driven adapter" (3, harness impls), "executor" (2, PTY + async), "preview caller" (dry-run).
   - Check every document. Any stale references to: "launch composition function," "single merge point," "single seam," "shared seam," "port" used loosely (e.g., "driving port" meaning call site), "Depth 2"/"Depth 3" labels, "9 driving ports," "8 driving ports"?
   - Does R05 describe its R06 dependency using the new vocabulary or old?
   - Does `harness-integration.md`'s discussion of `project_workspace()` match the new pipeline-stage framing?

2. **File-path reference consistency**
   - Explorer found `prepare_spawn_plan` is stale; the real pre-worker composer is `build_create_payload` at `ops/spawn/prepare.py:169-397`. Grep every design file for `prepare_spawn_plan`. Anywhere it still appears as the "current composer" or "driving port"? It's OK in historical references (scope evolution, rejected alternatives) but not as a live reference.
   - Grep for any reference to `run_streaming_spawn` that doesn't mark it as "deleted in R06."
   - Line numbers drift. Check sampled line-number citations (`app/server.py:333`, `streaming/spawn_manager.py:197`, etc.) against current code — are they still accurate? If R06 says `ops/spawn/execute.py:861` but the function is now at 870, it's stale.

3. **Numerical consistency**
   - Count of driving adapters: design should say **3** everywhere. Check for any "8 ports," "9 ports," "5 entry surfaces," etc.
   - Count of factory callers: **4** (3 drivers + dry-run), or **3** if dry-run is a path inside primary/worker rather than a distinct caller. The design should pick one and be consistent.
   - Count of executors: **2** (PTY + async). Verify.
   - Count of harness adapters: **3** (Claude, Codex, OpenCode). Verify.
   - R06 exit-criteria `rg` expected hit counts should match between `refactors.md`, the verification table in the report, and any restatement in `decisions.md`.

4. **Decision list coherence**
   - `decisions.md` lists D1-D18 per the "How this file is used" footer. Are all 18 present? Any gaps or duplicates?
   - Do references to decision IDs from spec/architecture files still resolve to existing decisions?
   - The "Rejected alternatives" in D17 — do they match prior iterations' discussion? Any contradictions with later decisions?

5. **Requirements traceability**
   - `requirements.md` has CFG-1, WS-1, CTX-1, SURF-1, BOOT-1. Each should be realized by at least one spec/architecture leaf. Check "Realizes" sections in architecture files and verify every EARS line has a home.
   - Changes to SURF-1.e6 and WS-1.e5 from prior rounds — are they reflected in architecture leaves that realize them?

6. **Scope section of R06**
   - R06 scope lists files it will touch. Are all those files real? Any listed paths that don't exist in `src/meridian/`?
   - Does the "Test blast radius" list match the deliverables? (If R06 deletes `run_streaming_spawn`, are tests that reference it in the test-blast-radius list?)

7. **Preamble dependency graph in `refactors.md`**
   - The preamble says R01/R02/R06 have no file-level overlap. Is that still true after the R06 rewrite? (The rewrite added type splits, deletions, fork absorption — check these don't touch files owned by R01 or R02.)

8. **Feasibility doc (`design/feasibility.md`)**
   - Does it still match current decisions? Any "OQ-N" items (open questions) that should be closed?
   - If the feasibility doc mentions "ports" or "composition seams" in language from earlier rounds, it's stale.

9. **Harness-integration.md's Launch composition section vs. refactors.md R06**
   - Both discuss the same architecture. Any wording where they disagree? Diagram in one, prose in the other — do they match?

10. **D17 vs R06**
    - D17 is the decision, R06 is the execution. They should agree on: driver count, executor count, factory caller list, deleted items, preserved divergences, fork treatment.
    - Any statement in D17 not backed by R06's scope? Any R06 scope item not justified in D17?

### What's out of scope for this check

- Whether the architecture is correct (other reviewers handle that).
- Whether the `rg` patterns are mechanically enforceable (other reviewers handle that).
- Whether there are missing driving adapters (other reviewers handle that).

Your lane is **coherence**: do the documents agree with each other?

### Report format

Structure:

1. **Per-document pass** — one short paragraph per document flagging stale vocabulary, stale file refs, or numerical drift. Clean documents get a single line: "refactors.md — clean."
2. **Cross-document contradictions** — list any statements that contradict between documents.
3. **Stale references** — file paths, function names, or line numbers that no longer match live code.
4. **Numerical mismatches** — counts that disagree across documents.
5. **Traceability gaps** — requirements without realizers, decisions without references, etc.
6. **Verdict** — `consistent` / `consistent-with-minor-fixes` / `inconsistent` with a one-sentence justification.

Be thorough. This is the last sweep before planning handoff; inconsistencies here become planner confusion and coder bugs. Target length: ~800 words.

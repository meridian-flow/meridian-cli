# Architect: origin-tagging field design for `SpawnFinalizeEvent`

## Context

Round 1 of the orphan-run reaper fix was rejected. One of the three blockers (F1, p1728 finding 1 and p1732 finding 1) is that **origin inference from `error` content is a heuristic**, not a mechanism:

- Round 1 proposed S-RP-004 (reaper stamps `succeeded` with `error=None` when a durable report exists) alongside S-PR-003 (projection infers terminal authority from `error` ∈ reconciler-error-set).
- These two rules contradict: a reconciler-authored `succeeded` has `error=None`, so S-PR-003 classifies it as runner-origin, and the later runner finalize cannot override it. The intended S-PR-001 repair path is broken.

Additionally (F5, p1728 finding 4 + p1732 finding 3): R-02 claimed "two-caller change" but there are **11 `finalize_spawn` writer sites**:

- `src/meridian/lib/launch/runner.py:851` — primary runner finalize (authoritative by direct exit evidence)
- `src/meridian/lib/launch/streaming_runner.py:1184` — streaming runner finalize (authoritative by direct exit evidence)
- `src/meridian/lib/launch/process.py:426` — process launch finalize of primary (authoritative by harness exit)
- `src/meridian/cli/streaming_serve.py:115` — CLI streaming serve finalize on user stop/completion (authoritative)
- `src/meridian/lib/app/server.py:145` — app server background_finalize by spawn_manager outcome (authoritative)
- `src/meridian/lib/app/server.py:256` — app server exception path (launch failure; runner never started)
- `src/meridian/lib/ops/spawn/execute.py:578` — background launch: params-persist failure (launch failure)
- `src/meridian/lib/ops/spawn/execute.py:637` — background launch: subprocess Popen failure (launch failure)
- `src/meridian/lib/ops/spawn/execute.py:881` — background worker failed to load params (launch failure)
- `src/meridian/lib/ops/spawn/api.py:493` — user-driven cancel
- `src/meridian/lib/state/reaper.py:57` — reconciler probe (only non-authoritative)

## What to design

Produce a design memo (1-2 pages) covering:

1. **Origin enum values.** Pick a small set. Propose: `runner` | `launcher` | `launch_failure` | `cancel` | `reconciler`. Justify each value's scope. The axis that matters for projection is **authoritative vs. best-effort probe**, but observability benefits from finer labels. Map each of the 11 writer sites to exactly one value (table form). Decide whether `runner` and `streaming_runner` share the `runner` label or deserve their own — same question for `launcher` vs. `app_background_finalize`. Bias toward fewest values that preserve the authority axis losslessly.

2. **Schema addition.** Add `origin` to `SpawnFinalizeEvent` (Pydantic model in `src/meridian/lib/state/spawn_store.py:153`). Default value choice — is `None` required for legacy events, or should new writes refuse `None`? Propose: `origin: SpawnOrigin | None = None` where `None` means "legacy, pre-origin-field row; infer via shim only". Spec out the `AUTHORITATIVE_ORIGINS` set that the projection uses.

3. **Projection authority rule.** Precise rule in the shape: "Projection replaces the terminal tuple (status, exit_code, error) only when the current projected origin is `reconciler` and the incoming event's origin is authoritative (∈ AUTHORITATIVE_ORIGINS)". All other combinations preserve first-wins. Metadata (duration, cost, tokens) merges always. Explicitly address: reconciler-over-reconciler (no-op), authoritative-over-authoritative (no-op), reconciler-over-authoritative (blocked). Include how the projection *records* the origin on the derived `SpawnRecord` — propose adding `terminal_origin: str | None` to `SpawnRecord` so subsequent events can check authority without re-scanning events.

4. **Legacy backfill shim (S-PR-003 demotion).** When the incoming event has `origin=None` (legacy row), infer: reconciler if `event.error ∈ {"orphan_run", "orphan_finalization", "missing_worker_pid", "harness_completed"}`, authoritative otherwise. Exact set stays isolated in one constant. Shim is read-only — never written — and has a planned deletion window (define one: "remove in version after N weeks of every current row having an origin field").

5. **Does origin belong on `SpawnUpdateEvent` too?** The runner's `mark_finalizing` update is a non-terminal transition. It conceptually has an origin (always runner), but the projection does not key off it today. Argue whether `SpawnUpdateEvent` gains an origin field or stays as-is. Default answer: stays as-is unless you can name a reconciler call path that emits a non-terminal `SpawnUpdateEvent`.

6. **Writer enumeration + instrumentation table.** Required output section: table with columns [writer_path_line, origin_value, authoritative?, comment]. All 11 writers. No writer left on origin=None in new code. This is the honest surface audit the reviewers asked for.

7. **Dead-code / deletion prompts.** S-PR-003 shrinks to a backfill shim — name the shim explicitly, define its removal window. `error`-based origin inference must not leak into any authoritative code path. Call out `exited_at`'s role change (it no longer distinguishes `orphan_finalization` vs `orphan_run` — that's now driven by `status == "finalizing"` per the parallel CAS design). Flag `exited_at` as a removal candidate for a later cycle but do not delete now.

## Evidence to consult

- `src/meridian/lib/state/spawn_store.py:317` — current `finalize_spawn`.
- `src/meridian/lib/state/spawn_store.py:534-586` — current projection (first-wins).
- All 11 writer sites listed above (read each to confirm the origin label is a faithful description of the writer's epistemic position, not a wish).
- Round 1 feedback: `.meridian/spawns/p1728/report.md` (findings 1 + 4), `.meridian/spawns/p1732/report.md` (findings 1 + 3).
- Round 1 rejected design: `.meridian/work/orphan-run-reaper-fix/design/architecture/overview.md`, `design/spec/overview.md`.
- Preservation hint: `.meridian/work/orphan-run-reaper-fix/plan/preservation-hint.md` (guiding document).

## Deliverable

Write the memo to:

`$MERIDIAN_WORK_DIR/arch-origin-memo.md`

Keep it tight. Include the full 11-writer table. Include the projection authority pseudo-code block. Call out removal candidates explicitly.

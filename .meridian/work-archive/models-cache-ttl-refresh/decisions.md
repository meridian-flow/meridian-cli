# Decisions — Models Cache TTL Refresh

Design-time decisions captured while reasoning was fresh. Implementation-
time decisions go in this same file (impl-orchestrator appends).

---

## D1: `ensure_fresh` is the single refresh entry point; `mars models refresh` routes through it

**Date:** 2026-04-06 (design)
**Context:** The first draft had `mars models refresh` bypass `ensure_fresh`
with its own lock+fetch+write path, to avoid a `force_ignore_offline`
escape hatch inside the helper.

**Decision:** Route `mars models refresh` through `ensure_fresh(Force)`,
where `Force` is defined to ignore `MARS_OFFLINE` coercion. `Auto` still
coerces to `Offline` when the env is set; `Force` does not.

**Why:** Review finding (opus, p1007) noted the bypass duplicates
lock+fetch+write logic and skips the double-check pattern. The
"force ignores offline" contract is actually *more* intuitive than
"offline means never fetch, period, and refresh is a special case."
One place to fix bugs is worth more than a slightly cleaner contract.

**Rejected alternative:** Keep the bypass to keep the helper contract
pristine. Rejected because duplication > contract purity when the
contract can be expressed as "Force always fetches."

---

## D2: Testability seam is `MARS_MODELS_API_URL`, not a `ModelFetcher` trait

**Date:** 2026-04-06 (design)
**Context:** First draft introduced `ensure_fresh_with` + `ModelFetcher`
trait for in-process fetch mocking, while phase 5 (integration tests)
needed a separate env-URL seam for cross-process stub injection.

**Decision:** One seam only — `fetch_models` reads `MARS_MODELS_API_URL`
with a fallback to `https://models.dev/api.json`. Unit tests and
integration tests both use `httpmock` + this env var. No trait, no
dual API.

**Why:** Review finding (opus, p1007) noted phase 5's concurrency test
requires real subprocesses, which a trait seam can't drive. Keeping
both seams means ~40 LoC of extra API surface and a hidden cross-phase
dependency (phase 5 assumed phase 2 added the env-URL seam but phase 2
described the trait approach). Collapsing to one seam eliminates both.

**Trade-off:** Env vars are process-global, so tests need
`#[serial_test::serial]` to avoid race conditions. Acceptable cost:
serial_test is a standard Rust pattern, and the affected tests are
a small bounded set.

---

## D3: Empty `models` array is always stale and unusable

**Date:** 2026-04-06 (design)
**Context:** First draft's `is_fresh` checked timestamp and TTL but
would accept a cache with `models=[]` if `fetched_at` was within TTL.

**Decision:** `is_fresh` returns `false` when `models.is_empty()`,
independent of timestamp. `is_usable` (for offline fallback) also
requires non-empty models. An "empty but fresh" cache never passes
either check.

**Why:** Reviews (gpt, p1005 and gpt52, p1006) both flagged that
`fetch_models` can return `Ok(vec![])` on API success with empty body,
and a user hand-crafting a cache file could create this state. Either
way, it reproduces the original "missing model" failure mode the
feature exists to fix. Fail closed.

**Downstream effect:** `ensure_fresh` with mode `Auto` on an
empty-but-timestamped cache will re-fetch. With mode `Offline` it will
return `ModelCacheUnavailable` — the same behavior as a truly empty
cache.

---

## D4: `read_cache_tolerant` wrapper for corrupt/missing files

**Date:** 2026-04-06 (design)
**Context:** First draft had `ensure_fresh` call the existing
`read_cache`, which hard-errors on JSON parse failure. A corrupt cache
would abort `ensure_fresh` before it could self-heal.

**Decision:** Introduce `read_cache_tolerant` that coerces any read
error (missing file, JSON parse, schema mismatch) to an empty cache.
`ensure_fresh` uses the tolerant wrapper. The strict `read_cache` stays
available for round-trip verification in the refresh path.

**Why:** Review finding (gpt, p1005) caught that `read_cache` hard-
errors on parse. The whole feature is about self-healing — tolerating
a corrupt file on read is essential to that.

---

## D5: Sync never aborts on refresh failure, but fetch has explicit timeout

**Date:** 2026-04-06 (design)
**Context:** Sync holds `sync.lock` for the full pipeline. If
`ensure_fresh` hangs on a slow models.dev endpoint during sync, every
concurrent sync stalls.

**Decision:**
1. `fetch_models` sets an explicit `ureq` connect+read timeout (15s
   each). This bounds worst-case sync stall to ~30s on a hung endpoint.
2. Sync catches all `ensure_fresh` errors and downgrades them to
   diagnostic warnings. Sync never fails because of a catalog refresh
   problem.

**Why:** Review finding (gpt, p1005) noted sync.lock + unbounded fetch
is a deadlock hazard. Review finding (gpt52, p1006) noted the
"sync never fails" invariant conflicts with `ensure_fresh` returning
`ModelCacheUnavailable`; we keep the invariant by catching the error
at the sync call site.

---

## D6: `MARS_OFFLINE` truthy values, not just presence

**Date:** 2026-04-06 (design)
**Context:** First draft checked `std::env::var_os("MARS_OFFLINE").is_some()`,
which treats `MARS_OFFLINE=0` as offline.

**Decision:** Introduce `is_mars_offline()` helper that parses the
value. Truthy: `1`, `true`, `yes` (case-insensitive, trimmed).
Everything else — including `0`, `false`, empty string, unset — is
not-offline. Requirements explicitly say `MARS_OFFLINE=1`.

---

## D7: Manual `Default for Settings` (not derive)

**Date:** 2026-04-06 (design)
**Context:** Initial configuration doc showed `#[derive(Default)]` on
`Settings` plus `#[serde(default = "...")]` on the new field. Review
caught that a missing `[settings]` table entirely yields
`Settings::default()`, which under derive would give
`models_cache_ttl_hours = 0` (= "always refresh"), not 24.

**Decision:** Switch `Settings` to a manual `Default` impl that mirrors
the serde field defaults. Any site that constructs via
`..Default::default()` now gets the right value.

---

## D9: Convergence call after review round 2

**Date:** 2026-04-06 (design)
**Context:** Reviewer p1008 returned "still needs changes" on round 2,
flagging four lingering inconsistencies between the decisions and the
docs:
1. Overview said `MARS_OFFLINE` coerces *every* `ensure_fresh` call
   (contradicting Force-ignores-offline).
2. `call-sites.md` opening sentence still mentioned a "lock primitive
   directly" path for `mars models refresh`.
3. Phase 1 still listed the rejected `derive(Default)` option as
   acceptable.
4. Phase 6 set list timeout to 30s while design said 60s for both.
5. Phase 4 still referenced the rejected `ensure_fresh_with` seam.

**Decision:** Apply all five fixes (mechanical wording sync — none
change architecture or interface). Treat the design as converged after
round 2 instead of running a third full review pass. The remaining
findings are lint-level, not architectural; another full reviewer pass
would consume time without uncovering new substance.

**Why no round 3 review:** The issues p1008 surfaced were stale text
in already-decided locations, not new design questions. The fix is
deterministic and inspectable in a single pass. Per orchestrator
guidance, "convergence is a judgment, not a checklist" — running
another reviewer to confirm five copy-edits is over-rotation.

**Risk if wrong:** The implementer reads a stale paragraph and
implements something inconsistent with decisions.md. Mitigation: each
phase blueprint links to decisions.md, and phase-2's review (per
staffing.md) will catch architectural drift before it ships.

---

## D10: Scoped dead-code sweep as Phase 0, broad sweep deferred

**Date:** 2026-04-06 (plan)
**Context:** The files Phases 1-6 will edit
(`mars-agents/src/models/mod.rs`, `src/cli/models.rs`, `src/cli/sync.rs`,
`src/sync/mod.rs`, and meridian's
`src/meridian/lib/catalog/model_aliases.py`, `catalog/models.py`) carry
residue from prior refactors — dead helpers, unused types, stale
comments, leftover scaffolding. Doing the cleanup inline during feature
phases would muddy the feature diffs and make review harder; doing no
cleanup would leave the feature work sitting on top of noise and risk
the feature coders "repairing" dead code by accident.

**Decision:** Insert a **Phase 0** before Phase 1 that is a
**scoped, deletions-only** sweep limited to those six files. Runs as
three sub-steps: refactor-reviewer identifies candidates → coder
applies deletions (no new abstractions, no behavioral changes) → two
reviewers (default + opus) verify safety against the P1-P6 blueprints.
Phase 0 fully converges before Phase 1 starts so every subsequent diff
reads against a clean baseline.

**Why scoped, not broad:** A workspace-wide dead-code sweep is
genuinely useful but has a different risk profile — it touches files
no one on this work item has loaded context for, and its reviewers
can't piggyback on the cross-phase safety check (which only makes sense
for files the feature work is about to edit). Bundling it into this
work item would either balloon scope or produce a sweep with weaker
review. A scoped sweep gets the baseline-cleaning benefit for this
feature without taking on the broader risk.

**Why Phase 0 and not Phase 5 (or later):** Doing the sweep *after*
the feature phases would mean reviewing P1-P6 diffs against a noisy
baseline (the original point of pain) and then asking reviewers to do
a second pass on the cleaned version. Front-loading the sweep is
strictly cheaper — the feature phases read and land against the final
shape of the code, and the sweep's own review only has to reason about
"safe to delete given what P1-P6 need," a question answerable *before*
P1 starts because the phase blueprints already exist.

**Follow-up queued:** A broad-sweep dead-code work item (workspace-wide
across mars-agents and meridian-channel, not limited to the six files)
is queued to start after this work item lands. The scoped sweep is not
a substitute — it's a prerequisite for this feature, and the broad
sweep is a separate piece of housekeeping.

**Rejected alternatives:**
- *Inline cleanup inside each feature phase.* Muddies diffs, weakens
  review, and forces every feature reviewer to also reason about
  deletions.
- *Skip entirely, do it all in the broad follow-up.* Leaves the
  feature work reading against noise and risks feature coders
  inadvertently "rescuing" dead code.
- *Do the broad sweep now as Phase 0.* Scope creep; the broad sweep's
  risk model doesn't match this work item's review capacity.

---

## D8: "Add then spawn" success criterion resolved via existing `mars add` sync

**Date:** 2026-04-06 (design)
**Context:** Requirements success criterion #2 says
"`meridian mars add` then immediately spawning an agent (skipping sync)
also works." On first read this looks contradictory: aliases only land
in `models-merged.json` via sync, so how can spawning "skip" sync?

**Resolution:** `mars add` already invokes sync internally (see
`../mars-agents/src/cli/add.rs:96,113`). The criterion is about
skipping an *additional explicit* `meridian mars sync` call after
`add`, not about skipping sync entirely. Phase 6 smoke test case 0
exercises this path.

**No design change needed** — flagged for traceability only.

---

## D11: Auto+fresh fast-path uses `effective_mode`, not original `mode`

**Date:** 2026-04-06 (impl, P2 review round 1)
**Context:** Reviewer p1025 (opus, design alignment) caught that `ensure_fresh` was checking `mode == Auto && is_fresh(...)` against the original argument before short-circuiting, instead of against `effective_mode`. Result: `MARS_OFFLINE=1` + fresh cache returns `AlreadyFresh`, but the design says Auto coerces to Offline first, so the correct outcome is `RefreshOutcome::Offline`.

**Decision:** The fast-path freshness check (and the under-lock re-check) must use `effective_mode`. Test #15 in the blueprint asserted the original (incorrect) behavior; update it to expect `RefreshOutcome::Offline` (or `AlreadyFresh` is still acceptable if cache is fresh — design doc says "return offline_or_error(cache)" for Offline mode, which returns `Offline` outcome on usable cache).

**Why:** The whole point of the offline coercion is to make Offline behavior consistent regardless of how the caller arrived at it. Treating MARS_OFFLINE differently from `Offline` once we're past the coercion line undermines that.

---

## D12: `resolve_refresh_mode` no longer collapses MARS_OFFLINE into Offline

**Date:** 2026-04-06 (impl, P2 review round 1)
**Context:** Reviewer p1023 (gpt-5.2, error paths) found that `resolve_refresh_mode(no_refresh_flag)` returned `Offline` when *either* the flag *or* `MARS_OFFLINE` was set. Then `offline_unavailable_reason(Offline)` always reports the `--no-refresh-models` reason. The "MARS_OFFLINE is set..." reason became unreachable from any CLI call site that goes through the helper.

**Decision:** `resolve_refresh_mode` returns `Offline` ONLY when the flag is set. The MARS_OFFLINE coercion happens inside `ensure_fresh` itself (Auto → Offline). The error-reason helper distinguishes the two cases by inspecting both the requested mode AND `is_mars_offline()` at error time.

Concretely:
- `resolve_refresh_mode(true)` → `Offline` (flag-only)
- `resolve_refresh_mode(false)` → `Auto` (env-handling deferred to ensure_fresh)
- `offline_unavailable_reason(Offline)` → flag reason
- `offline_unavailable_reason(Auto)` (after coercion) → MARS_OFFLINE reason

**Why:** Two distinct user-visible reasons require two distinct triggers. Collapsing them into one mode loses the cause information.

---

## D13: Failed-fetch coalescing via sidecar timestamp

**Date:** 2026-04-06 (impl, P2 review round 1)
**Context:** Reviewer p1022 (gpt-5.4, concurrency) found that on a fetch outage, the lock+double-check pattern doesn't help: caller A acquires the lock, fetches, fails, releases the lock returning StaleFallback. Caller B (waiting) acquires the lock, re-reads the same stale cache (still stale), and tries to fetch *again*. With N waiters, an outage produces N serialized fetch attempts (each up to 30s), not one.

**Decision:** When `ensure_fresh` falls back to a stale cache after a failed fetch under the lock, atomically write a sidecar file `.mars/.models-cache.last-fail` containing the current unix timestamp. In `ensure_fresh`, after the under-lock re-check but before initiating a fetch, read this sidecar: if it exists and is within the last 300 seconds (5 minutes), skip the fetch and return `StaleFallback { reason: "recent fetch attempt failed; backing off" }` (or the original reason from the sidecar if cached).

`Force` mode bypasses the sidecar check (Force always tries).

**Why:** A short cooldown gives the system breathing room without permanently masking the failure. 5 minutes is short enough that a transient outage self-heals after the next read past the cooldown window. Sidecar file (not a new field on `ModelsCache`) preserves the D8 contract that `ModelsCache`'s serialized shape stays unchanged.

**Test:** Update the concurrency test to add a barrier: spawn N threads, all blocked on a mutex that holds them at the door, release them simultaneously, assert exactly 1 fetch hit on the stub. Plus a new test: stub returns 500, two callers, assert exactly 1 fetch attempt and both get StaleFallback.

---

## D14: P2 nits (non-blocking) folded into D11/D12/D13 fix

**Date:** 2026-04-06 (impl, P2 review round 1)

Three small fixes to apply alongside the blocking ones:
- `read_cache_tolerant` switches from `cfg!(debug_assertions) + eprintln!` to `tracing::debug!` (matches design spec).
- Stale-fallback warning message has a doubled "failed: fetch failed:" — collapse to a single phrase.
- Concurrency test #19 gets a barrier (see D13 test plan).

---

## D15: Empty-catalog response also triggers cooldown sidecar

**Date:** 2026-04-06 (impl, P2 review round 2)
**Context:** Both p1028 (gpt-5.4) and p1029 (opus) flagged that the round-1 D13 fix only writes the fail-cooldown sidecar on `Err(...)` from `fetch_models`, not on the `Ok(empty_catalog)` path. Since `fall_back` treats both as failures, the cooldown should treat both as failures too. As-is, an upstream that persistently returns `Ok([])` allows the same N-waiter fetch storm D13 set out to prevent.

**Decision:** The `Ok(empty)` branch passes `mark_fetch_failure = true` to `fall_back`, so the sidecar gets written and subsequent waiters within the cooldown window short-circuit on stale.

**Override:** p1028 also flagged "D12 has no production caller yet" as blocking. That's expected — phases 3 and 4 add the CLI call sites for `resolve_refresh_mode`. P2 ships the helper; P3/P4 wire it. Not a P2 blocker.

---

## D16: ensure_fresh_19 flake fixed by private injected-fetcher seam

**Date:** 2026-04-06 (impl, P3/P4 parallel verification)
**Context:** The barrier-gated concurrency test ensure_fresh_19_concurrent_auto_refresh_hits_api_once failed consistently under default cargo parallelism (mock.hits() == 2 while refreshed == 1, already_fresh == 1 — an impossible-looking state caused by some combination of httpmock counter race and timing under high CPU load). Passed at --test-threads=4 and in isolation.

**Decision:** Introduce a private (non-pub) ensure_fresh_with_fetcher helper inside src/models/mod.rs that accepts an injected fetch closure. Refactor the test to use an AtomicUsize counter and channel-based sequencing instead of Barrier + httpmock.hits(). The coalescing assertion remains strict (exactly 1 fetch, 1 Refreshed, 1 AlreadyFresh).

**Why (not a D2 regression):** D2 rejected a public ModelFetcher trait that would add 40 LoC of API surface. The new helper is private to the module — it exists solely to make the test deterministic and is invisible to downstream callers. Net LoC cost is much smaller than the trait approach would have been.

---

## D17: run_list --json must mirror run_resolve's JSON error envelope for ModelCacheUnavailable

**Date:** 2026-04-06 (impl, P3 review round 1)
**Context:** All three P3 reviewers (p1036, p1037, p1038) flagged that run_list calls ensure_fresh(...)? and lets ModelCacheUnavailable bubble to top-level CLI dispatch, which prints a plain stderr 'error: ...' line. run_resolve already special-cases the same error into a {"error": ...} JSON envelope. This broke JSON-consumer contracts for any automation calling 'mars models list --json'.

**Decision:** run_list matches on the ensure_fresh result and, in JSON mode on ModelCacheUnavailable, writes the JSON error envelope to stdout and returns exit code 1. Non-JSON mode still propagates the error via ?.

---

## D18: Unknown-alias check happens before ensure_fresh in run_resolve

**Date:** 2026-04-06 (impl, P3 review round 1)
**Context:** p1036 caught that run_resolve's new ordering refreshes the cache before validating that the requested alias exists in the merged config. Alias existence is a function of models-merged.json, not the models cache, so the refresh is unnecessary for the unknown-alias path. Worse, when offline with no cache, a typo now returns ModelCacheUnavailable instead of the original 'unknown alias' error — a visible regression in error clarity.

**Decision:** run_resolve loads merged aliases first and returns the unknown-alias error immediately if the alias isn't found. Only after the alias is known does it call ensure_fresh. Unknown-alias errors are now hermetic (no cache/network touched).

---

## D19: StaleFallback warning surfaced at CLI layer, not library layer

**Date:** 2026-04-06 (impl, P3 review round 1)
**Context:** P2 removed the 'warning: models cache refresh ...' eprintln from fallback_to_stale_or_error (correctly — policy belongs in CLI, not in the library helper). But run_refresh / run_list / run_resolve then ignored RefreshOutcome::StaleFallback and reported success. p1036 caught this as a real regression for 'mars models refresh' — the command would say 'done.' while silently using stale cache after a fetch failure.

**Decision:** Every CLI call site that invokes ensure_fresh must match on RefreshOutcome and surface StaleFallback explicitly:
- Human mode: eprintln a 'warning: models cache refresh failed: {reason}; using stale cache' message to stderr.
- JSON mode: include a 'cache_warning' field in the response (success or error branches), mirroring the pattern used by list/resolve success JSON.

'mars models refresh' additionally returns a non-zero-ish status in JSON ('cache_warning' present) so automation can detect the degraded state.

---

## D20: P5 hermeticity — clear MARS_CACHE_DIR in subprocess helpers

**Date:** 2026-04-06 (impl, P5 review round 1)
**Context:** P5 reviewer p1048 caught that the integration-test helpers configure_assert_cmd / configure_std_cmd isolated HOME and XDG_* but did not touch MARS_CACHE_DIR, which mars-agents' src/source/mod.rs prefers over HOME for global cache discovery. If a test runner happened to inherit MARS_CACHE_DIR from the host shell, sync tests could escape the temp sandbox.

**Decision:** Both helpers now env_remove("MARS_CACHE_DIR") on every spawned mars subprocess, so tests are hermetic regardless of host-shell state.

---

## D21: P5 coverage — Scenario F rewritten to actually exercise Req 1; Scenario H added for Req 2

**Date:** 2026-04-06 (impl, P5 review round 1)
**Context:** P5 reviewer p1047 (gpt-5.2) noted the original Scenario F asserted only file existence after 'mars sync --force' on a fresh empty project — it didn't model the actual failure mode (dependency-provided alias + cold cache → resolve fails). Requirements 1 and 2 were not really being exercised.

**Decision:** Scenario F was rewritten to:
1. create a local-source 'package' dir with mars.toml [package] + [models.test-alias],
2. mars init the test project,
3. mars add the local source,
4. mars sync --force,
5. mars models resolve test-alias against the stub catalog and assert success,
6. assert .mars/models-merged.json contains test-alias.

Plus new Scenario H ("add immediately resolve without explicit sync") covers Req 2 by running mars add (which internally syncs), then immediately resolve, with one fetch hit asserted.

The original concurrency scenario was renamed to scenario_i_concurrent_processes_fetch_once (the J reordering followed). All scenarios now have stronger assertions (cached model id present in list output, no cache file on failure paths, JSON parsing of concurrent stdout).

---

## D22: P6 timeout rationale corrected — mars caps each HTTP phase, not total

**Date:** 2026-04-06 (impl, P6 review round 1)
**Context:** P6 reviewer p1051 caught that the meridian-side timeout comment said mars HTTP is '~30s max (15s connect + 15s read)', which is wrong — mars actually configures three independent 15-second phases (timeout_connect + timeout_recv_response + timeout_recv_body), so worst-case is closer to 45s.

**Decision:** Comment in both _run_mars_models_list and run_mars_models_resolve corrected to mention all three phases. The 60s subprocess timeout is unchanged — it still leaves headroom over the corrected 45s ceiling, plus DNS / disk / process startup.

Smoke doc Case 5 also fixed to use the concrete .mars/models-cache.json path instead of an undefined mars_dir variable, with a stat-based mtime hint for the human tester.

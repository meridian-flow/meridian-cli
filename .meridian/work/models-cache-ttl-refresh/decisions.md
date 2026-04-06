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

# Streaming Parity Fixes v3 — Run Report

## Verdict

Converged. All eight implementation phases are committed, the final multi-lane review loop converged across runtime, types, refactor, and design-alignment lanes, and all four verification gates are green (ruff clean, pyright 0 errors, 563 tests passing in normal and `PYTHONOPTIMIZE=1` modes). Ready to close the work item.

## Scope

v3 re-shaped the streaming/subprocess parity contract around the Round-3 "coordinator, not policy engine" reframe. The keeper invariants K1–K9 landed as code: a `(harness_id, transport_id)`-keyed `HarnessBundle` registry with eager-import bootstrap and drift guards (K1–K3, K9), a non-optional `PermissionResolver` threaded end-to-end with no harness parameter (K4), `RuntimeContext.child_context()` as the sole producer of `MERIDIAN_*` child overrides with fail-closed rejection on both `plan_overrides` and `preflight.extra_env` (K5), harness-owned extractors wired into both subprocess and streaming paths (K6), frozen `PermissionConfig` / `MappingProxyType` env views (K7), and idempotent cancel/interrupt semantics with first-terminal-status-wins finalize (K8). Meridian no longer strips user passthrough flags, no longer validates `PermissionConfig` combinations, and no longer special-cases harness-ids in shared dispatch — every strict check left in the codebase exists to protect meridian's own internal drift, not to second-guess users or harnesses.

## Commits

### Implementation (Phase 1–8)

| SHA | Phase | Summary |
|---|---|---|
| `7ad7dce` | 1 | Contract leaves + adapter ABCs |
| `759d6a3` | 2 | Launch spec + permission pipeline |
| `9b2cfee` | 3 | Claude projection + preflight parity |
| `ba5283c` | 4 | Codex subprocess + streaming parity |
| `86172bf` | 5 | OpenCode transport parity |
| `81e0d6b` | 6 | Shared launch context + env invariants |
| `9641c55` | 7 | Bundle bootstrap + extractors + projection convergence |
| `b52b4ac` | 8 | Runner + spawn-manager + REST lifecycle convergence |

### Final review fix pass

| SHA | Coder | Summary |
|---|---|---|
| `86073df` | p1519 | Streaming runner F1/F2/F3 completion/signal races + `HarnessBinaryNotFound` diagnostics preserved through finalize |
| `728ec5f` | p1520 | Extract `runner_helpers.py`, dedupe session-extractor scanner, delete dead `extract_session_id_from_artifacts` alias |
| `b0eea6d` | p1520 | Types/contracts: bundle registry immutability, Codex `--allowedTools` drop warning, narrowed bootstrap `ImportError` swallow, Codex `HarnessCapabilityMismatch` subclasses `ValueError` |
| `db7eb89` | p1524 | Streaming runner F2 residual race when completion and signal tasks land on the same `asyncio.wait` wakeup |

## Review loop

### Round 1 — 4-way fan-out across diverse model families

| Lane | Reviewer | Spawn | Findings |
|---|---|---|---|
| Runtime | gpt-5.4 | p1515 | F1 completion-task race; F2 late-signal race; F3 missing-binary diagnostics regression |
| Types | gpt-5.2 | p1516 | M-1 `HarnessCapabilityMismatch` not `ValueError`; M-2 Codex `--allowedTools` silent drop; M-3 `HarnessBundle` mutable |
| Refactor | claude-sonnet-4-6 | p1518 | C1 D19 line-budget breach; H1 6 duplicated helpers; H2 dead alias; M1/M3/M4 |
| Design | claude-opus-4-6 | p1517 | M-1 D19 breach; M-2 dual adapter registry; M-3 silent bootstrap `ImportError` swallow; 5 lows |

Fix coders split the work: p1519 owned the runtime race fixes; p1520 owned the types/contracts fixes and the refactor extraction in two separate commits.

### Round 2 — scoped re-review

| Lane | Spawn | Verdict |
|---|---|---|
| Runtime re-review | p1521 | F1 closed, F2 **not** fully closed (residual same-wakeup race), F3 closed with minor caveat |
| Types re-review | p1522 | All 4 findings closed cleanly |
| Refactor re-review | p1523 | H1, H2, M1, M4, D19 deferral all closed |

### Round 3 — F2 residual convergence

Fix coder p1524 landed the residual same-wakeup ordering fix (`terminal_event_future` → `completion_task` → `signal_task` branch priority plus forced `_await_terminal_outcome_after_completion(...)` inside the completion branch, with a regression test that forces the exact interleaving). Runtime re-re-reviewer p1525 confirmed the race is now fully closed with no new findings.

## Gates

All four gates green post all fix commits (orchestrator-run on `db7eb89`):

| Gate | Result |
|---|---|
| `uv run ruff check .` | All checks passed |
| `uv run pyright` | 0 errors, 0 warnings, 0 informations |
| `uv run pytest tests/ --ignore=tests/smoke -q` | 563 passed |
| `PYTHONOPTIMIZE=1 uv run pytest tests/ --ignore=tests/smoke -q` | 563 passed (pytest `-O` warning only) |

## Scenarios

All seven Phase 8 scenarios verified end-to-end:

- **S014** — Resolver threaded through `run_streaming_spawn(...)` and REST `/api/spawns`; no `cast("PermissionResolver", None)` remaining; identity-preserving invariant `spec.permission_resolver is resolver` holds.
- **S027** — Signal handling parity across runners (re-verified via direct test counts after verifier concurrency artifact; see E8.7).
- **S028** — `HarnessBinaryNotFound` raised with parity fields across all 6 matrix cells (3 harnesses × 2 runners).
- **S035** — Bundle dispatch single runtime narrow; no `if harness_id == ...` branches in shared dispatch.
- **S041** — `send_cancel()` / `send_interrupt()` idempotent across all four connection types.
- **S042** — SIGTERM streaming parity across harnesses; subprocess variant scoped to library coverage per E8.8.
- **S048** — Cancel vs completion race: exactly-one terminal status persisted; first-winner finalize semantics.

Earlier phase scenarios (S001–S013, S015–S026, S029–S034, S036–S040, S043–S047, S049–S054) were verified in their owning phases and remain green under the final gate run.

## Deferred

Items found during the final review loop and explicitly accepted out of v3 scope. Each has a decision-log entry under E9.11 or E9.13.

- **D19 / C1 / Design M-1** — Runner line-budget breach. `runner.py` (865 lines post-H1 extraction) and `streaming_runner.py` (1174 lines post-H1 extraction) remain above the 500-line target. Full L11 decomposition along finalize/retry/event-pump axes deferred to a follow-up work item. See E9.11.
- **Design M-2** — Dual adapter registry. `HarnessRegistry` + `HarnessBundle._REGISTRY` both hold adapter refs. Not a correctness bug because adapters are stateless; follow-up should route lookups through `get_harness_bundle(harness_id).adapter`. See E9.11.
- **L-4** — `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` routing through two parallel channels. Functionally equivalent; "won't fix in v3". Originally deferred in E3.1, retained through E6.3 and E7.7. See E9.11.
- **L-5** — S033 streaming-projection log-shape inconsistency. Claude has managed-flag collision detection; Codex/OpenCode emit generic passthrough logs. Contract passes literally. See E9.11.
- **L-6** — Dead `except AttributeError` in `launch/context.py`. Unreachable with the `BaseHarnessAdapter.preflight` default; cleanup postponed. See E9.11.
- **L-7** — `TransportId.SUBPROCESS` enum value unused — only `STREAMING` is registered in bundles. Aspirational and non-harmful. See E9.11.
- **L-8** — S042 subprocess variant unreachable from user flow because `supports_bidirectional=True` routes all CLI spawns through streaming. See E8.8 and E9.11.
- **Refactor M3** — Test parametrization for per-harness triples in `test_streaming_runner.py`. Non-blocking structural follow-up.
- **F3 minor caveat** — `HarnessBinaryNotFound` structured fields (`binary_name`, `searched_path`) are preserved as stringified text in `error` rather than promoted to first-class row fields. User-visible diagnostics are functional. See E9.11 and E9.12.

## Judgment calls

Orchestrator-level decisions made during the loop (distinct from individual coder fixes):

- **Fan-out composition.** Round 1 used four genuinely diverse model families (gpt-5.4, gpt-5.2, claude-opus-4-6, claude-sonnet-4-6) with four different lens assignments (runtime, types, refactor, design-alignment) to avoid correlated blind spots. The per-lens split produced strictly disjoint finding sets and confirmed there was no single-model review bias.
- **Fix staffing.** p1519 and p1520 were split by commit intent, not by reviewer lane, so that runtime-race fixes landed as one atomic commit while structural refactor and types fixes stayed decoupled. This kept each commit bisect-friendly and made the review-2 scoping trivial per commit.
- **Convergence stopping criterion.** Round 3 was launched narrowly on the F2 residual only (not a full re-fan-out) because round-2 runtime review (p1521) was the only lane that returned "not fully closed", and all other lanes (p1522, p1523) cleanly converged. Spawning another design or types reviewer would have added no new information.
- **S027 verifier concurrency artifact (E8.7).** The verifier was squeezed between unit-tester edits in Phase 8 and observed a transient failing state. Orchestrator re-verified S027 directly via test counts rather than respawning; respawning would have replayed the same race without new signal.
- **S042 smoke re-verify skipped (E8.9).** After p1504 reran the smoke driver with post-fix evidence, orchestrator did not respawn an independent `@smoke-tester` because evidence was objective JSON rows in `spawns.jsonl`. Pragmatic on process overhead, strict on invariants.
- **Deferral choices.** D19, Design M-2, L-4/L-5/L-6/L-7/L-8, and Refactor M3 were accepted out-of-scope on the explicit criterion "not a runtime correctness defect and not blocking v3 invariants". Each deferral has a concrete follow-up hook recorded in decisions.md so the next work item can pick them up without rediscovery.
- **D19 decomposition vs. runtime fixes.** When the final review surfaced both runtime races and the line-budget breach, orchestrator chose to land runtime fixes first and defer decomposition. Decomposition is a pure refactor with no behavioral change; runtime correctness was load-bearing. Splitting monolithic runners without a fresh design pass would have introduced risk disproportionate to the benefit within this cycle.

## Follow-ups

What the next work item should pick up:

- **L11 runner decomposition.** Split `runner.py` and `streaming_runner.py` into ≤500-line units along finalize / retry / event-pump axes. Requires a short design pass to pick the axis cleanly; touching both monoliths at once is the highest-leverage cleanup now that the parity contract is stable.
- **Dual adapter registry unification.** Retire `HarnessRegistry` by routing every adapter lookup through `get_harness_bundle(harness_id).adapter`. Small scope, no behavior change, but closes Design M-2.
- **`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` consolidation.** Move routing fully onto `preflight.extra_env` per the original E3.1 plan, eliminating the plan-overrides branch.
- **`HarnessBinaryNotFound` structured row fields.** Promote `binary_name` and `searched_path` from error-text to first-class fields on persisted terminal rows so `meridian spawn show` can render them structurally.
- **Test parametrization.** Convert per-harness triples in `test_streaming_runner.py` to `pytest.mark.parametrize` per the refactor-reviewer's M3.
- **S033 log-shape unification.** Add managed-flag collision detection to Codex and OpenCode streaming projections so all three transports emit the same passthrough debug-log shape.
- **Runner import style normalization.** `runner.py` uses relative imports from `runner_helpers`, `streaming_runner.py` uses absolute. Minor, low-priority cleanup.

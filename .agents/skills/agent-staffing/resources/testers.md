# Testers

Different testers cover different failure modes. Verification (tests, lints, type checks via the verifier) is the baseline. Beyond that, match testing to what the phase touches.

## Default Lanes

**smoke-tester** — default for any phase touching process boundaries, state initialization, CLI behavior, IPC, or fresh-state workflows. Unit tests and type checks verify internal correctness, but orchestration bugs — process lifecycle, file locking, IPC, fresh-state initialization — only surface when real processes run in real environments. These are exactly the bugs that ship to users because "all tests passed." When the honest test requires a temp repo, temp config, temp server, or tiny helper script, the smoke-tester should build it in a disposable scratch environment and prove the workflow end-to-end.

**browser-tester** — default for any phase touching frontend behavior. The frontend equivalent of smoke-tester — verifies that UI changes actually work in a real browser, not just that component tests pass. Visual correctness, user flows, form interactions, console errors, and accessibility. When the honest test requires fresh state, a stub API, or a temp config, build it rather than testing against whatever happens to be running.

## Situational

**unit-tester** — for tricky logic, contracts between modules, edge cases, and regression guards. Not every phase needs new unit tests — but when there's complex logic that's hard to verify end-to-end, targeted unit tests pin down the behavior.

# Testers

Different testers cover different failure modes. Verification (tests, lints, type checks via the @verifier) is the baseline. Beyond that, match testing to what the phase touches.

Testers are not limited to the @coder's described checks. Generate independent edge cases, failure modes, and boundary-condition probes based on the change itself.

## Default Lanes

@verifier — baseline for every implementation phase. Runs tests, type checks, and lints. Fixes mechanical breakage (import errors, type mismatches), reports substantive failures. Run this lane alongside @smoke-tester and @unit-tester when those lanes are warranted by the change.

@smoke-tester — default for any phase touching process boundaries, state initialization, CLI behavior, IPC, or fresh-state workflows. Unit tests and type checks verify internal correctness, but orchestration bugs — process lifecycle, file locking, IPC, fresh-state initialization — only surface when real processes run in real environments. These are exactly the bugs that ship to users because "all tests passed." When the honest test requires a temp repo, temp config, temp server, or tiny helper script, the @smoke-tester should build it in a disposable scratch environment and prove the workflow end-to-end. Do not stop at the happy path — smoke-test realistic edge cases and failure paths as a default lane. **For integration phases** (code that talks to external binaries, APIs, or wire protocols), smoke testing is the only verification that matters — you must run against the real external system and test every supported target, not just one. Explicitly report which targets were tested and which were not.

@browser-tester — default for any phase touching frontend behavior. The frontend equivalent of @smoke-tester — verifies that UI changes actually work in a real browser, not just that component tests pass. Visual correctness, user flows, form interactions, console errors, and accessibility. When the honest test requires fresh state, a stub API, or a temp config, build it rather than testing against whatever happens to be running.

@unit-tester — for tricky logic, contracts between modules, edge cases, and regression guards. Not every phase needs new unit tests — but when there's complex logic that's hard to verify end-to-end, targeted unit tests pin down the behavior. Generate edge cases independently; don't only codify scenarios handed over by the coder. When a phase introduces new interfaces, protocols, or state machines (extraction protocols, lifecycle handoffs, retry logic), unit tests are the gate — don't rely solely on smoke tests to catch contract violations.

## Situational

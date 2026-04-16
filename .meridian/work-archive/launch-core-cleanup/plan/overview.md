# Plan Overview

## Parallelism posture

Sequential implementation, parallel verification/review.

Reason:
- Launch cleanup is structurally coupled around one composition surface.
- Source edits overlap heavily across launch factory, spawn prepare/execute, request DTOs, and primary-launch helpers.
- Parallel coder lanes would conflict on same files without buying real schedule reduction.

## Rounds

### Round 1 - Implementation

One `coder` lane edits launch composition, DTO cleanup, consistency fixes, and extension-seam documentation in one coherent patch.

### Round 2 - Mechanical verification

Run `verifier` on changed files plus repo-wide `ruff`, `pyright`, targeted tests, and broader test suite as needed to restore green.

### Round 3 - Final review fan-out

Run three `reviewer` lanes, all `gpt-5.4`:
- invariant compliance
- consistency/types/naming
- DRY/duplication/extension seams

Fix findings with `coder`, rerun `verifier`, rerun reviewers until convergence.

## Refactor handling

- Refactor is in-scope, not deferred: remove preview-path composition from `prepare.py`, remove wrapper DTO constructor, merge/rename duplicate runtime context, centralize artifact constants, and make workspace projection dispatch explicit.
- Do not expand into full primary/spawn launch architecture redesign beyond requested seam cleanup.

## Staffing

- `coder`: implement single cleanup patch from blueprint.
- `verifier`: baseline green lane after coder.
- `reviewer` x3 on `gpt-5.4`: invariant compliance, consistency, DRY.
- `smoke-tester`: only if verifier finds launch behavior needs explicit runtime CLI confirmation beyond targeted tests.

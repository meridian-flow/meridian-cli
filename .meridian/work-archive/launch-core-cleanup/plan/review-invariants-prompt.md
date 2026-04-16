# Review Brief - Invariant Compliance

Review launch-core-cleanup for semantic invariant compliance.

Use only `gpt-5.4`.

Read:
- `.meridian/work/launch-core-cleanup/requirements.md`
- `.meridian/invariants/launch-composition-invariant.md`
- `.meridian/work/launch-core-cleanup/plan/pre-planning-notes.md`
- changed launch/spawn/harness files

Focus:
- all 13 invariants, especially I-1, I-2, I-3, I-5, I-8, I-9
- prohibited driving-adapter calls
- executor composition drift
- process/fork-path exceptions
- spawn-manager or primary-launch residual alternate composition surfaces

Output findings first, with severity and file:line references. If clean, say so explicitly.

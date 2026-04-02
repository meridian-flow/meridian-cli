# Decision Log — Mars Structural Refactor

## D1: Defer F20 (link.rs split) and F18 (MarsContext extraction)

**Decided:** Skip both findings from this pass.

**Reasoning:** F20 (link.rs is 788 lines) would split scan logic into `src/link/scan.rs`. But link.rs isn't growing — no pending features touch it. The split moves code without reducing complexity. F18 (MarsContext to library module) matters when there's a non-CLI consumer. There isn't one. Both carry refactoring risk for no immediate payoff.

**Alternatives rejected:**
- Include F20: Adds a new module boundary, tests to port, and increases review surface for no correctness or readability win today.
- Include F18: Creates a `src/context.rs` module that only the CLI uses. Premature abstraction.

## D2: Remove DepSpec.items rather than wire it up

**Decided:** Remove the dead field entirely.

**Reasoning:** Wiring up items-level dependency filtering interacts with collision detection, frontmatter rewriting, and the target build in non-obvious ways. The field currently does nothing — users who set it get no filtering. Removing it is honest (no false API promise) and safe (no runtime behavior change). Re-adding it when the feature is ready is straightforward.

**Alternative rejected:** Leave the field with a `// TODO` comment. Dead schema with comments is still dead schema — the parser accepts it, the runtime ignores it, and users think it works.

## D3: Don't merge check.rs and doctor.rs discovery into one function

**Decided:** Extract `discover_installed()` for doctor.rs only. Leave check.rs with its own discovery logic.

**Reasoning:** Check validates raw source packages (pre-install, no lock, stricter rules like name/filename match). Doctor validates installed managed roots (has lock, includes unmanaged files, runs skill-dep checks). Despite superficial similarity (both scan agents/*.md), they operate on different inputs with different semantics. A shared function would need branching on context, which is worse than two focused functions.

## D4: Fallback to "no match" instead of "first entry" for cross-package skill rename

**Decided:** When no same-source or dependency match is found, leave the skill reference unchanged (skip rewrite).

**Reasoning:** The current `entries.first()` fallback picks an arbitrary renamed skill, which may be wrong. Leaving the reference unchanged is safer — the original skill name won't resolve on disk (it was renamed), and `mars doctor` will flag it. This gives the user a clear diagnostic rather than silently pointing at the wrong skill.

**Alternative rejected:** Error on no match. This would fail sync for a case that's currently survivable. The agent installs fine — it just has a broken skill reference that doctor can detect.

# Redesign Pass: Cwd-First Bootstrap, No Implicit Walk-Up Adoption

You are revising the existing design package for work item `mars-add-bootstrap-design`.

## Inputs

Read and revise against these existing artifacts:

- `requirements.md`
- `design/spec/bootstrap-behavior.md`
- `design/architecture/implementation.md`
- `design/feasibility.md`
- `design/refactors.md`
- `redesign-feedback-init-centric.md`
- `redesign-feedback-no-walkup.md`

## Goal

Keep the init-centric model, but revise the design so write/bootstrap target selection is strictly cwd-first unless the user explicitly passes `--root`.

This redesign is specifically about `mars init` and auto-init-capable commands such as `mars add`.

## Hard Constraints

1. `mars init` is the canonical bootstrap primitive.
2. `add` may auto-initialize by reusing `init` semantics.
3. The default target for `init` is `cwd`.
4. The default target for `add` auto-init is `cwd`.
5. `--root` is the only override for selecting a different write/bootstrap target.
6. No implicit ancestor `mars.toml` discovery may be used to choose where `init` or auto-init writes state.
7. Nested mars projects are normal and must remain safe.
8. The design must explicitly work on macOS, Linux, and Windows.
9. Git must not be a prerequisite for bootstrap or target selection.

## Required Revision

Revise the design so that:

- `mars init` acts on `cwd` by default and does not adopt an ancestor project.
- `mars add` auto-init, if config is considered missing for the chosen target, initializes at `cwd` by default and does not adopt an ancestor project.
- If parent discovery is retained anywhere, it must be explicitly scoped as a separate read/detect concern, not as write-target selection.
- The spec and architecture stop framing ancestor walk-up as the primary resolution path for first-use bootstrap.

## Questions To Resolve

The revised package should answer:

1. For `mars add`, if an ancestor `mars.toml` exists but none exists in `cwd`, should the command attach to the ancestor or initialize `cwd`?
   My expected direction: do **not** silently adopt the ancestor for write/bootstrap flows.
2. Should read-only or context-dependent commands still use parent discovery?
   It is acceptable to keep this as a separate concern, but do not let it control bootstrap target selection.
3. What precise messaging should users see when `add` initializes `cwd` while an ancestor mars project also exists?
4. How should `--root` interact with both existing config and auto-init?

## Output Requirements

Overwrite the active design package in place. Do not create a parallel draft tree.

At minimum, update:

- `design/spec/bootstrap-behavior.md`
- `design/architecture/implementation.md`
- `design/feasibility.md` if assumptions changed
- `design/refactors.md` if implementation seams changed
- `decisions.md` with any material design reversals

## Scope Discipline

- Do not broaden this into a full repo-wide de-git program.
- Do not broaden this into a full repo-wide Windows compatibility program.
- You may name those as follow-on tracks, but the design itself must make bootstrap/root selection correct on all three platforms now.

## Success Condition

The revised design should be internally consistent and should clearly separate:

- bootstrap/write-target selection
- optional parent discovery for read/detect flows
- explicit override behavior via `--root`

If the current package already contains assumptions that conflict with these constraints, replace them rather than preserving them.

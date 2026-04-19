## Redesign Feedback: No Implicit Walk-Up Adoption

The current init-centric design still keeps too much ancestor-config behavior for write/bootstrap flows.

### New Direction

For `mars init` and any auto-init-capable command, the default target must be `cwd`.

### Required Rule

- No implicit walk-up adoption for `init`
- No implicit walk-up adoption for auto-init flows like `add`
- `--root` is the only override for choosing a different target

### Why

- Nested `mars` projects are common enough to treat as normal, not edge cases.
- Silently adopting an ancestor `mars.toml` makes nested projects unsafe and surprising.
- Creation/bootstrap commands in other tools generally act on `cwd`, not on discovered parent state.

### Clarification

This feedback is specifically about write/bootstrap target selection.

It does **not** require removing all parent discovery from every read command in the product.
The design question here is narrower:

- where `init` creates state
- where auto-init creates state
- whether `add` should silently adopt a parent project

### Expected Revision

Revise the design so that:

1. `mars init` uses `cwd` by default
2. `mars add` auto-init, if allowed, uses `cwd` by default
3. `--root` is the explicit escape hatch
4. Ancestor `mars.toml` discovery is not used to choose the write target

If parent discovery is retained anywhere, it must be framed as a separate read/detect concern, not implicit target selection.

---

## Resolution

**Status**: Addressed in design package revision.

| Feedback Item | How Addressed |
|---------------|---------------|
| `init` uses cwd by default | Spec INIT-2; Architecture `find_root_for_write` uses cwd directly |
| `add` auto-init uses cwd by default | Spec AUTO-1; Architecture `find_root_for_write` (no walk-up) |
| `--root` is explicit escape hatch | Spec ROOT-1, AUTO-4; decisions D5 |
| Ancestor discovery not used for write target | Spec "Explicit Prohibitions" section; Architecture uses `find_ancestor_config` only for warning |
| Parent discovery framed as separate concern | Spec "Separation of Concerns" table; Architecture has `find_root_for_context` for read commands |

Key design changes:

1. **Dual-path root selection**: `find_root_for_write` (cwd-only) vs `find_root_for_context` (walk-up) — see decisions D18, D20
2. **Explicit prohibition on implicit adoption**: Spec now includes "Explicit Prohibitions" section
3. **Ancestor warning is read-only**: `find_ancestor_config` runs after target is already determined
4. **All files updated**: requirements, spec, architecture, feasibility, refactors, decisions

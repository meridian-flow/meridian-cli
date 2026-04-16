# Refactor Agenda

No structural refactors required. All changes are localized:

- Profile YAML edits are frontmatter-only with no cross-file dependencies.
- Profile prompt edits are body text within individual profile files.
- The `_permission_flags_for_harness()` change is a one-line mapping fix.
- The contradiction warning is an additive check in `resolve_permission_flags()`.

No preparatory rearrangement is needed before feature work.

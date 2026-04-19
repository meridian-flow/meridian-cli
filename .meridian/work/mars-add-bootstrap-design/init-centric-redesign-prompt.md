Revise the `mars-add-bootstrap-design` package around an init-centric model.

The current design is too `add`-specific.

New direction:
- `mars init` is the canonical bootstrap primitive.
- Define an explicit allowlist of subcommands that may auto-initialize when config is missing.
- `add` should follow that model instead of having one-off bootstrap behavior hidden inside root lookup.

What to produce:
- Update the existing design package so bootstrap semantics are defined in terms of init semantics and an auto-init allowlist.
- Clarify which commands may auto-init and which must still fail on missing config.
- Keep cross-platform behavior visible.
- Do not solve the full repo-wide de-git pass or full repo-wide Windows compatibility program inside this feature design.
- Instead, name those as follow-on design tracks after bootstrap semantics are settled.

Important scoping:
1. Bootstrap semantics
   - make `mars init` the canonical bootstrap path
   - define the auto-init allowlist
   - make `add` follow that model
2. Remove accidental git assumptions
   - separate follow-on design track
3. Repo-wide Windows compatibility
   - separate follow-on design track

Replace the current bootstrap framing with this model and produce an updated design package.

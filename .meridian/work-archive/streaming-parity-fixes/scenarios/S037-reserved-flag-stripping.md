# S037: Reserved-flag stripping (RETIRED)

- **Source:** design/permission-pipeline.md reserved-flags policy (revision rounds 1–2)
- **Added by:** @design-orchestrator (revision pass 1)
- **Retired by:** @design-orchestrator (revision round 3, reframe)
- **Replaced by:** [S045](S045-extra-args-forwarded-verbatim.md)
- **Status:** retired

## Retirement rationale

Revision round 3 deletes all reserved-flag machinery (`_RESERVED_CODEX_ARGS`, `_RESERVED_CLAUDE_ARGS`, `strip_reserved_passthrough`, and the `projections/_reserved_flags.py` module). `extra_args` is forwarded verbatim to every transport.

Meridian is a coordinator, not a security gate. Stripping flags from user passthrough provides a false sense of security (the user could invoke the harness directly) and silently surprises users when their intended flag disappears. The correct behavior is to forward `extra_args` verbatim and let the harness decide what to do with it.

See `decisions.md §Revision Pass 3` entries H1 and `design/edge-cases.md §E48` for the replacement invariant.

## Result (filled by tester)
_retired — do not execute_

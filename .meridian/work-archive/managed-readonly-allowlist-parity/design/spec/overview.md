# Spec Overview — Managed Read-Only + Tool Allowlist Parity

Behavioral contract: any profile or CLI spawn that declares
`sandbox: read-only` **and/or** an explicit tool list
(`tools: [...]` or `disallowed-tools: [...]`) gets that enforcement on
**codex**, **claude**, and **opencode**. No silent drops.

## Leaf files

- `enforcement.md` — cross-harness fail-closed contract (E-*).
- `codex.md` — codex-specific enforcement claims (SC-*).
- `claude.md` — claude-specific enforcement claims (SL-*).
- `opencode.md` — opencode-specific enforcement claims (SO-*).
- `dryrun.md` — dry-run surfacing requirements (SD-*).

## Statement ID prefixes

| Prefix | Scope |
|--------|-------|
| `E-`   | Cross-harness uniform behavior (fail-closed, contract) |
| `SC-`  | Codex enforcement |
| `SL-`  | Claude enforcement |
| `SO-`  | OpenCode enforcement |
| `SD-`  | Dry-run surfacing |

All statement IDs are stable; implementation's `leaf-ownership.md` references
these exact IDs.

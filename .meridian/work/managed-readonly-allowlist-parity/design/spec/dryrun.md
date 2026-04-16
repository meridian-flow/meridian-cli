# Spec — Dry-Run Surfacing (`SD-*`)

`meridian spawn --dry-run` is the contract surface where users verify what
meridian will actually do. Enforcement must be visible here.

## SD-1 Codex dry-run surfaces CODEX_HOME and config.toml

When `meridian spawn --dry-run --harness codex` is invoked with an
enforcement-carrying profile, the dry-run output shall include:
(a) the path meridian would materialize as `CODEX_HOME` (under
`.meridian/spawns/<spawn_id>/codex-home/`), and
(b) the full body of the generated `config.toml` that would be written
to that path.

## SD-2 Claude dry-run surfaces plan-mode and denylist union

When `meridian spawn --dry-run --harness claude` is invoked with
`sandbox: read-only`, the dry-run output shall include the projected
`--permission-mode plan` flag and the full `--disallowedTools` argument
list (union of profile denylist and read-only mutating-tool list).

## SD-3 OpenCode dry-run surfaces OPENCODE_PERMISSION

When `meridian spawn --dry-run --harness opencode` is invoked with
enforcement-carrying profile, the dry-run output shall include the
effective `OPENCODE_PERMISSION` env value as a JSON string.

## SD-4 Capability-mismatch is surfaced before command output

When the dry-run request would trigger `HarnessCapabilityMismatch` (per
E-1/E-2/E-3), the dry-run shall report the mismatch and shall not emit a
stub command line that pretends enforcement is in place.

## SD-5 No new secrets in dry-run

The dry-run surface shall not print the contents of copied auth material
(`auth.json`, `.credentials.json`); it shall reference those files by
path only.

# OpenCode Parity

## Scope

OpenCode launch-parity for biomed MVP:

- session capture
- continue/fork semantics
- report extraction
- Google model fidelity
- effort mapping
- smoke coverage

## Current understanding

- Meridian's streaming OpenCode path uses `opencode serve` plus the HTTP session/message API, not an OpenCode compaction plugin.
- The documented `.opencode/plugins/meridian.ts` plugin is not needed for normal spawn execution. Existing docs that claim it exists should be treated as stale unless the feature is intentionally revived.
- Preferred fix direction: `harness-native-profile-projection` should be the path to full parity, especially for OpenCode permission/config semantics.
- The launch-core refactor materially changed OpenCode parity status:
  - env/config projection now exists through `OPENCODE_CONFIG_CONTENT` and `OPENCODE_PERMISSION`
  - but parity is not fully fixed, especially on the streaming path
  - older notes that described OpenCode as having no config-style projection at all are stale
  - remaining live issues are concentrated in runtime fidelity, permission semantics, and readback behavior

## Findings to preserve

### Current implementation status

- Partially implemented by refactor:
  - OpenCode workspace/config projection via `OPENCODE_CONFIG_CONTENT`
  - OpenCode permission override projection via `OPENCODE_PERMISSION`
  - this is not the same thing as proven parity for streaming permission semantics
- Still true runtime gaps:
  - OpenCode streaming ignores `effort` override
  - OpenCode streaming still explicitly logs that permission resolver overrides are ignored at projection time
  - session-file lookup is environment-sensitive in storage helpers, but later adapter/session-log resolution drops the original launch env
  - live OpenCode report extraction does not capture the useful assistant text for current terminal/event shape
- Replaced by more precise issues:
  - continue/fork is no longer a single generic gap; subprocess projection now emits `--session`/`--fork`, while streaming still cannot express `continue_fork`, and live fork behavior is still broken
  - model fidelity is no longer “Meridian mangles the requested model string”; live smoke suggests Meridian preserves the request, but OpenCode exports different provider/model metadata for these runs
- Lower-priority limitations that still exist:
  - OpenCode subprocess rejects per-spawn `mcp_tools`
  - OpenCode subprocess has no native skills flag; skills must come from prompt/session content or OpenCode-native discovery
  - storage discovery is hard-coded to `session_diff/` and `session/`

### Docs / smoke coverage findings

- Docs that claim OpenCode compaction reinjection via `.opencode/plugins/meridian.ts` are stale.
- Public docs that imply OpenCode handles "anything else" are too broad; routing is pattern-based.
- Smoke docs overstate OpenCode skill-injection coverage; existing smoke coverage is weaker than the docs imply.
- OpenCode runtime behavior has stronger unit/parity coverage than live smoke coverage.
- Existing smoke docs understate the live OpenCode failure mode: continuation lost session context and live fork hung, not just the known effort asymmetry.
- Existing notes should stop saying config/permission parity is fixed; the accurate claim is that env/config projection machinery now exists and must be validated against actual OpenCode behavior.

## Open questions

- Whether streaming fork should move to the documented OpenCode fork API instead of session-create semantics.
- How `harness-native-profile-projection` should materialize OpenCode-native agent/profile/config state so `OPENCODE_PERMISSION` and `OPENCODE_CONFIG_CONTENT` reflect the intended semantics on the live `opencode serve` path.
- Whether transcript lookup should persist the resolved storage root or session file path at launch time.
- Whether report extraction should prefer official OpenCode export/API surfaces over storage-file heuristics.
- Whether the live model-fidelity issue is an OpenCode-side routing/defaulting problem, a Meridian transport mismatch, or both.

## Evidence sources

- `.meridian/spawns/p1903/report.md`
- `.meridian/spawns/p1905/report.md`
- `.meridian/spawns/p1908/report.md`
- `.meridian/spawns/p2137/report.md`

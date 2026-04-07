# CLI `--help` Gap Analysis

The new `__meridian-cli` skill points at `--help` as the canonical reference. That's only honest if `--help` actually contains what the old skills documented. This doc enumerates the gaps and the proposed additions.

The fixes are **prerequisite** to the consolidation: the help text gets updated *before* the old skills are deleted. Otherwise an agent following the new skill's pointers lands on inadequate text.

These additions live in the meridian source tree (`src/meridian/cli/...`) and the mars source tree, not in the skill bodies. Implementation is part of phase 1 of the eventual plan.

## Gap 1 — `meridian --help` (top-level) is missing command groups

Current top-level help lists only `mars`, `spawn`, `work`, `models`. Missing:

- `session` — subcommand group exists (`session log`, `session search`)
- `config` — subcommand group exists (`config get/set/show/init/reset`)
- `doctor` — top-level command exists

`report` is correctly *not* a top-level — it lives under `spawn`, and the existing parenthetical "`spawn    Create and manage subagent runs (includes report subgroup)`" already surfaces it. No change needed for `report`.

**Add to top-level Commands list:**

```
session  Read and search harness session transcripts
config   Repository config inspection and overrides
doctor   Health check and orphan reconciliation
```

## Gap 2 — `meridian doctor --help` is one line

Current text: `Spawn diagnostics checks.`

This is the command the consolidation skill points agents at for "first move when state looks weird." It needs to actually describe what doctor does.

**Proposed body:**

```
Health check and auto-repair for meridian state.

Reconciles orphaned spawns (dead PIDs, stale heartbeats, missing
spawn directories), cleans stale session locks, and warns about
missing or malformed configuration.

Doctor is idempotent — re-running converges on the same result.
It is safe (and intended) to run after a crash, after a force-kill,
or any time `meridian spawn show` reports a status that doesn't match
reality.

Examples:
  meridian doctor                  # check and repair, JSON output
  meridian doctor --format text    # human-readable summary
```

## Gap 3 — `meridian session --help` and its subcommands are bare

Current `meridian session --help` lists `log` and `search` with one-line descriptions. Missing the principles agents need: ref types, parent inheritance, compaction segments.

**Add a one-paragraph preface** to `meridian session --help`:

```
Inspect harness session transcripts.

Session refs accept three forms: chat ids (c123), spawn ids (p123),
or raw harness session ids. By default, commands operate on
$MERIDIAN_CHAT_ID — inherited from the spawning session — so a
subagent reads its parent's transcript, not its own.
```

**Add to `meridian session log --help`:** explicit examples covering `-n`, `-c`, and `--offset`, plus the rule that `-c 0` is the latest segment and higher numbers walk backward.

**Add to `meridian session search --help`:** an example showing the navigation hint output and noting the search is case-insensitive.

## Gap 4 — `meridian work sessions --help` is short but not broken (enrichment, not gap)

Current help already says: *"List sessions associated with a work item. Default shows active sessions; use --all for historical."* That is a real use-case description, not just a flag table.

This entry is **enrichment, not a gap-fill.** Optional one-line addition that ties it to the broader workflow:

```
Combined with `meridian session log`, this is the way to walk
a work item's full conversation history across multiple runs.
```

Lower priority than Gaps 1–3 — the existing one-liner is good enough that the new `__meridian-cli` skill can legitimately point at it without this enrichment. Land it if cheap; skip if not.

## Gap 5 — `meridian spawn report --help` examples are wrong

Current help on `meridian spawn report` and `meridian spawn report create` shows examples for `meridian spawn -m ... -p ...` — they were copy-pasted from the parent group and never customized. Replace with report-specific examples:

```
meridian spawn report show p107
meridian spawn report search "auth bug"
echo "Report body" | meridian spawn report create --stdin
```

## Gap 6 — `meridian spawn --help` doesn't explain `--from`

`--from` accepts a prior spawn or session ref to inherit context (report and files). Today the flag is listed with one line. Add:

```
--from REF   Inherit context from a prior spawn or session.
             Pulls in the prior spawn's report and any files it
             touched. Repeatable. Use when the new spawn needs
             the *reasoning* from a prior conversation, not just
             its artifacts.
```

## Gap 7 — `meridian mars --help` is mostly fine

`mars --help` already produces a usable command list and brief descriptions. The only addition needed is one line at the top:

```
Bundled with meridian — invoke as `meridian mars <subcommand>`
or directly as `mars <subcommand>` if installed standalone.
```

Subcommand-level help is good enough as-is. If a subcommand is missing examples, that's a mars-side improvement and can be filed separately — not a blocker for this consolidation.

## Gap 8 — `mars.toml` schema reference has no replacement home

The deleted `__mars/` skill linked to `resources/mars-toml-reference.md` containing the full TOML schema. D8 in `decisions.md` says the new `__meridian-cli` ships without `resources/`. Without explicit action, the schema reference vanishes.

Resolution options, in preference order:

1. **Confirm `mars init --help` (or a new `mars schema` / `mars init --schema` flag) renders the schema.** Cleanest fix. If absent, this becomes a small mars source-tree edit. The planner picks whether to bundle the mars work or defer.
2. **Preserve `mars-toml-reference.md` under `__meridian-cli/resources/`.** Bends D8 but keeps the consolidation moving. Requires amending the decision-log entry to allow this single resource if option 1 isn't viable.
3. **Move the reference into `meridian-base/README.md` or a top-level docs file.** Least preferred — READMEs are not loaded at agent runtime, so an agent editing `mars.toml` cannot consult them.

Status today: option 1's command does not exist. Default fallback is option 2 unless mars work gets bundled in.

## Gap 9 — `mars version --help` should include the release workflow

The deleted `__mars/` skill walked through the version-bump workflow: `mars version patch` → commits → tags → optional `--push`, plus the precondition that the working tree must be clean and the requirement for a `[package]` section in `mars.toml`. Confirm `mars version --help` covers this end-to-end. If only the bump verbs are listed without the surrounding workflow, add a short preface to that subcommand's help.

Verification step before phase 1: run `mars version --help` and confirm. If adequate, no source edit. Otherwise this is a one-line docstring change in mars.

## Gap 10 — `meridian config --help` is bare

Current text lists subcommands without saying what config controls. Add a preface:

```
Repository-level config (`.meridian/config.toml`) for default
agent, model, harness, timeouts, and output verbosity.

Resolved values are evaluated independently per field — a CLI
override on one field does not pull other fields from the same
source. Use `meridian config show` to see each value with its
source annotation.
```

## What Is NOT a Gap

These were considered and judged sufficient as-is:

- `meridian models list` — its output already includes routing guidance. The `__meridian-cli` skill table routes agents past the bare `meridian models --help` group help directly to `list`, which is honest because that's where the useful content actually lives.
- `meridian work --help` — subcommand list is complete and self-explanatory.
- `meridian work sessions --help` — see Gap 4 (enrichment, not gap).
- `meridian spawn show/list/log` — current help is sufficient for the new skill's purposes.
- `mars` subcommand-level help — adequate for the "point and learn" pattern, except for the items called out in Gaps 8 and 9.

## Implementation Notes for the Plan

Most gaps are one-file edits (or small handfuls) in `src/meridian/cli/`. **Gaps 8 and 9 cross repo boundaries — they are mars-side, not meridian-side.** The planner bundles them with the meridian-cli edits if mars work is in scope for this consolidation; otherwise, apply Gap 8 option 2 (preserve the resource under `__meridian-cli/resources/`) and verify Gap 9 only (no source edit if `mars version --help` already covers the workflow).

The whole help-text expansion lands as one phase that runs *before* the skill deletions, so an agent following an in-progress consolidation never lands on a stale help text.

Verification for that phase: run each updated `--help` and confirm the new content appears. No code tests needed — these are docstrings.

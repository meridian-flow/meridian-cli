# Decision Log: Sandbox Simplification

## D1: Remove PermissionTier entirely vs. keep as optional hint

**Decision**: Remove `PermissionTier` enum entirely. Sandbox is `str | None` everywhere.

**Reasoning**: The enum provides no value — it doesn't prevent harness errors (Codex rejects `unrestricted` regardless of whether meridian validates it), and it prevents valid harness values (`none` for Codex) from being used. The translation from string -> enum -> string is pure overhead.

**Alternative rejected**: Keep `PermissionTier` as a "known values" hint with passthrough for unknown values (parse unknown strings as a raw passthrough). Rejected because this is complexity for no benefit — the "hint" would just be documentation, and documentation belongs in docs/help text, not in runtime validation code.

**Alternative rejected**: Move validation into each harness adapter (`CodexAdapter.validate_sandbox()`). Rejected because validation at launch time (when Codex rejects the flag) is sufficient and requires zero code. Adding adapter-level validation recreates the maintenance burden in a different location.

## D2: Rename `tier` to `sandbox` in PermissionConfig

**Decision**: Rename `PermissionConfig.tier` to `PermissionConfig.sandbox`.

**Reasoning**: The field is no longer a "tier" in an abstract hierarchy. `sandbox` matches the field name everywhere else: CLI `--sandbox`, profile YAML `sandbox:`, `RuntimeOverrides.sandbox`, `execute.py` parameter name. One name everywhere reduces cognitive overhead.

**Constraint discovered**: The field name `tier` appears in test assertions (`config.tier is PermissionTier.WORKSPACE_WRITE`). These all need updating, but they're straightforward string comparisons after the change.

## D3: Remove KNOWN_SANDBOX_VALUES validation from RuntimeOverrides AND settings.py

**Decision**: Remove the `_validate_sandbox` validator from both `RuntimeOverrides` (overrides.py) and `PrimaryConfig` (settings.py), making sandbox behave like `model` and `harness` (free-form passthrough strings).

**Reasoning**: `model` and `harness` are both free-form strings validated by their consumers. Sandbox should follow the same pattern. The validator currently rejects `none` (a valid Codex sandbox value) and accepts `unrestricted` (which Codex rejects).

**Reviewer finding (p882, p883)**: Initial design missed `settings.py`'s independent `_validate_sandbox` validator. Without removing it, `meridian.toml` config would still reject free-form sandbox values even though CLI and env vars pass through. Both reviewers flagged this as the primary gap.

## D4: Keep approval mode system unchanged

**Decision**: Don't touch approval modes (`yolo`/`auto`/`confirm`/`default`).

**Reasoning**: Approval modes work correctly today. They're a known, harness-independent set with well-defined translations for each harness. The translation logic in `permission_flags_for_harness()` for approval modes is correct and tested. Mixing this change with approval changes would increase risk for no benefit.

## D5: Don't update agent profiles in .agents/

**Decision**: Don't modify agent profile YAML files in this change.

**Reasoning**: `.agents/` is generated output from submodules. The existing sandbox values (`read-only`, `workspace-write`, `unrestricted`) need updating in source submodules. Profiles using `sandbox: unrestricted` that target Codex will still fail — this design removes the false validation layer, not the profile misconfiguration. Fixing profiles is a separate change in `meridian-dev-workflow/` submodule.

## D6: Keep TieredPermissionResolver name (revised)

**Decision**: Keep `TieredPermissionResolver` name unchanged. Don't rename to `SandboxPermissionResolver`.

**Reasoning**: Both reviewers noted the rename adds churn across 6 test files without reducing abstraction count. The class is a one-field wrapper over `permission_flags_for_harness()`. Renaming it is cosmetic and increases the diff surface of the change. If the wrapper is ever removed (simplification reviewer suggested this as an option), the name becomes moot.

**What changed**: Initial design proposed renaming. Reviewers correctly identified this as churn-for-no-benefit. Keeping the name means 5 test files that import `TieredPermissionResolver` need zero changes.

## D7: BackgroundWorkerParams serialization (migration note)

**Decision**: Accept the serialized field name change from `permission_tier` to `sandbox`.

**Reasoning**: `BackgroundWorkerParams` is serialized to disk for background spawns. Renaming the field means in-flight spawns queued before upgrade will deserialize with `sandbox=None` (Pydantic ignores unknown fields), losing their sandbox setting. Per CLAUDE.md: "No backwards compatibility needed." In practice, background spawns are short-lived and unlikely to span upgrades.

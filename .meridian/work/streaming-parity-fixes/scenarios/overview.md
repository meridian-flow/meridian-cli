# Scenarios — Master Index

Every edge case in `design/edge-cases.md` is represented here.

Revision round 3 adds S039–S051 for the new meridian-internal invariants (K1–K9) and retires S037 (reserved-flag stripping) in favor of S045 (verbatim forwarding). The round-3 **convergence pass** adds S046b (`plan_overrides` MERIDIAN_* leak) and S052 (mechanical K4 guard on `PermissionResolver.resolve_flags` signature).

## Status Values

- **pending**
- **verified**
- **failed**
- **skipped**
- **retired** (revision round 3 — no longer applicable)

## Index

| ID | Title | Tester | Status |
|---|---|---|---|
| S001 | Adapter omits `resolve_launch_spec` override | @unit-tester | pending |
| S002 | Base `ResolvedLaunchSpec` passed to Claude dispatch | @unit-tester | pending |
| S003 | Caller passes `None` as `PermissionResolver` | @verifier | pending |
| S004 | Resolver lacks `.config` | @unit-tester | pending |
| S005 | New Claude spec field forgotten in projection | @unit-tester | pending |
| S006 | New SpawnParams field forgotten in factory accounting | @unit-tester | pending |
| S007 | Streaming Codex with `sandbox=read-only` | @smoke-tester | pending |
| S008 | Streaming Codex with `approval=auto` | @smoke-tester | pending |
| S009 | Streaming Codex with `approval=default` | @smoke-tester | pending |
| S010 | Streaming Codex confirm rejection emits event | @smoke-tester | pending |
| S011 | Streaming Claude resolver-internal `--allowedTools` dedupe | @smoke-tester | pending |
| S012 | Subprocess Claude dedupe parity | @smoke-tester | pending |
| S013 | REST POST missing permission metadata behavior | @smoke-tester | pending |
| S014 | `run_streaming_spawn` with caller-supplied resolver | @smoke-tester | pending |
| S015 | Claude full-field round-trip (incl. `mcp_tools`) | @unit-tester | pending |
| S016 | Codex permission matrix semantics | @unit-tester | pending |
| S017 | OpenCode model prefix normalization | @unit-tester | pending |
| S018 | OpenCode skills single-injection | @smoke-tester | pending |
| S019 | Codex `report_output_path` streaming behavior | @unit-tester | pending |
| S020 | `continue_fork=True` without session id | @unit-tester | pending |
| S021 | Claude subprocess/streaming arg-tail parity | @unit-tester | pending |
| S022 | User `--append-system-prompt` passthrough collision | @unit-tester | pending |
| S023 | `--allowedTools` from resolver + user `extra_args` forwarded verbatim | @unit-tester | pending |
| S024 | `LaunchContext` parity (deterministic subset only) | @unit-tester | pending |
| S025 | Parent Claude permissions forwarded identically | @smoke-tester | pending |
| S026 | No duplicate runner constants | @verifier | pending |
| S027 | `python -O` preserves guard behavior | @verifier | pending |
| S028 | Harness binary missing from PATH | @smoke-tester | pending |
| S029 | Invalid codex app-server passthrough surfaced cleanly | @smoke-tester | pending |
| S030 | Projection completeness guard at import | @unit-tester | pending |
| S031 | No circular imports | @verifier | pending |
| S032 | Confirm-mode rejection event ordering | @unit-tester | pending |
| S033 | Streaming passthrough debug logs | @unit-tester | pending |
| S034 | `OpenCodeConnection` inherits `HarnessConnection` | @verifier | pending |
| S035 | Unified connection interface conformance | @unit-tester | pending |
| S036 | Delegated field has no consumer | @unit-tester | pending |
| S037 | Reserved-flag stripping (RETIRED → S045) | — | retired |
| S038 | Codex fail-closed capability mismatch | @smoke-tester | pending |
| S039 | Duplicate harness bundle registration raises `ValueError` | @unit-tester | pending |
| S040 | Protocol/ABC method-set reconciliation | @unit-tester | pending |
| S041 | `send_cancel` idempotency across transports | @unit-tester | pending |
| S042 | SIGTERM parity across subprocess and streaming | @smoke-tester | pending |
| S043 | Missing extractor in bundle fails registration | @unit-tester | pending |
| S044 | New `SpawnParams` field unclaimed by any adapter fails at import | @unit-tester | pending |
| S045 | `extra_args` forwarded verbatim to every transport | @unit-tester + @smoke-tester | pending |
| S046 | `preflight.extra_env` containing `MERIDIAN_*` key raises | @unit-tester | pending |
| S046b | `plan_overrides` containing `MERIDIAN_*` key raises (symmetric to S046) | @unit-tester | pending |
| S047 | `mcp_tools` projected into every harness wire format (OpenCode subprocess rejects non-empty) | @unit-tester | pending |
| S048 | Cancel vs completion race — exactly one terminal status | @unit-tester | pending |
| S049 | Streaming session-id fallback via `HarnessExtractor` | @smoke-tester | pending |
| S050 | `(harness, transport)` dispatch for unsupported transport raises | @unit-tester | pending |
| S051 | `PermissionConfig` is frozen after construction | @unit-tester | pending |
| S052 | `PermissionResolver.resolve_flags` stays harness-agnostic (mechanical guard, K4) | @unit-tester | pending |

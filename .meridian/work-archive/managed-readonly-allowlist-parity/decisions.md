# Decisions

Append-only. Each entry answers what was decided, why, and what was rejected.

## D1 — Answers to requirements.md open questions

### Q1: Is Claude `--permission-mode plan` alone sufficient for read-only?

**Decision:** No. Combine `--permission-mode plan` **and** an explicit disallow list
`--disallowedTools Edit,Write,MultiEdit,NotebookEdit,Bash,WebFetch` whenever
meridian projects `sandbox: read-only` onto the claude harness.

**Why:**
- `plan` mode is a UX hint — it instructs the model to plan and wait for
  approval before executing. In non-interactive `-p` runs there is no human to
  approve the plan, so nothing strictly blocks the model from calling a
  mutating tool if it decides to skip the plan phase. Upstream docs (p1724)
  note `plan` as a planning-focused restriction, not a hard permission check.
- The permission precedence documented for claude (p1724) says `--disallowedTools`
  is honored and `deny` at higher scope cannot be overridden by `--allowedTools`.
  That is the mechanism that actually blocks tool invocation.
- Running both gives an aligned signal to the model *and* a hard enforcement
  layer. Belt-and-suspenders, not redundant — each fails differently.

**Rejected:** denylist-only. That loses the planning nudge; agents that
otherwise try to `Edit` fail loudly instead of switching to a read-path
equivalent, producing worse agent output.

### Q2: Per-spawn codex `CODEX_HOME` — inherit user config or isolate?

**Decision:** Fully isolated by default. `CODEX_HOME` points at
`.meridian/spawns/<spawn_id>/codex-home/` containing only meridian-generated
`config.toml`. For authentication, meridian **copies or symlinks** the
auth-material files it knows about (`auth.json`, `.credentials.json`) from the
user's real `~/.codex` **if they exist**. Nothing else is inherited — no
`config.toml`, no `history.jsonl`, no MCP server definitions, no logs.

**Why:**
- Reproducibility: two spawns with the same profile must produce identical
  codex config regardless of what the human has configured locally.
- Fail-closed surface area: a user-level `config.toml` could enable features
  or apps that meridian's projection intended to block. Merging is a silent
  hole; isolation keeps the blast radius tight.
- Auth is a separate concern from policy. Auth material is copy-narrow (two
  known filenames) and failing to copy it would break login, which is a worse
  footgun than "policy can silently leak".
- Matches `streaming-parity-fixes` S046 ethos: `CODEX_HOME` was added as an
  explicit `preflight.extra_env` key for exactly this purpose.

**Rejected:**
- Full inheritance (include user `config.toml`): defeats the point of the
  allowlist work; any user-level `[features] apps = true` overrides our lock.
- Full isolation including auth: would require re-login per spawn. Unworkable.

**Opt-out:** a future `--codex-inherit-user-config` flag can layer user config
on top; out of scope for this work.

### Q3: Codex allowlist — features+apps+permissions alone, or per-app blocks too?

**Decision:** For this work, managed allowlist means the pair
`(sandbox_mode, approval_policy) + [features].* = false` for broad feature
cuts + `[apps._default].enabled = false` to disable app tools globally +
`[permissions.<name>]` profile for filesystem/network shape. No per-app or
per-tool blocks generated beyond disabling the `_default` bucket.

**Why:**
- Codex builtins that matter for "read-only" intent (file read, shell under
  sandbox, grep-ish) are gated by `sandbox_mode = read-only`, not by
  per-tool toggles. The sandbox is the enforcement layer; per-tool config is
  a finer-grained knob that does not strengthen the read-only guarantee.
- Symmetry with claude's per-tool allowlist is intentionally not pursued:
  codex's upstream schema (p1729) does not expose a symmetric per-builtin
  toggle matrix. Trying to synthesize one by generating per-tool blocks for
  every claude tool name would invent a schema codex does not honor.
- The profile `tools:` list still gets recorded in meridian metadata and
  surfaced in `--dry-run`, so the intent survives; codex just cannot reject
  individual builtin tool names the way claude does.

**Rejected:**
- Synthesize `[apps.<name>.tools.<tool>.enabled = false]` stanzas for each
  missing tool from the profile. Requires knowing every codex app's tool
  catalog at meridian-build-time and would drift with every codex release.
- Translate profile `tools:` → `allowedTools` CLI flag. That is exactly the
  current silent-strip path; it does not work.

### Q4: Reject at spawn time, or warn-and-degrade?

**Decision:** Fail-closed at spawn preparation. If a profile declares an
enforcement axis (`sandbox: read-only` or an explicit `tools:` / `disallowed-tools:`
list) and the selected harness adapter cannot satisfy it, meridian raises
`HarnessCapabilityMismatch` before any harness process is launched.

**Why:**
- The entire point of the work is to end "silent strip". Degrading to a warning
  leaves the user with the same footgun in a different costume.
- The three harnesses all have *a* mechanism that covers both axes once this
  design lands, so the failure surface after implementation is limited to:
  (a) an older harness version below the declared floor, or (b) a user hitting
  `sandbox: default` which is "no opinion" and still passes through.
- Spawn-time is the cheapest moment to fail. Discovering the gap mid-run costs
  a wasted model call and leaves partial state.

**Rejected:** warn-and-degrade. That is the current behavior and it is what
the requirements explicitly call out as the problem.

**Passthrough exception:** `sandbox: default` and empty tool lists mean
"no meridian opinion"; those still pass through silently by design.

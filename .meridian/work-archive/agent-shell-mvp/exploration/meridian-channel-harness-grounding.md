`meridian spawn report create --stdin` failed because the sandbox is read-only for `.meridian/spawns/p1106/`, so this is the required fallback report.

**Grounding**
Date: `2026-04-07`  
Repo: `/home/jimyao/gitrepos/meridian-channel`

I read the harness layer, spawn/launch flow, prompt assembly, permission mapping, transcript/session code, and state layer. No files were modified.

**Top Conclusion**
The current harness abstraction is built around one launched process producing one completed run. It already has useful session-related hooks like resume/fork/session-id detection, but it does not model a persistent bidirectional transport.

The core contract in [adapter.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/adapter.py#L23) is:

```python
class HarnessCapabilities(BaseModel):
    """Feature flags for one harness implementation."""

    model_config = ConfigDict(frozen=True)

    supports_stream_events: bool = True
    supports_stdin_prompt: bool = False
    supports_session_resume: bool = False
    supports_session_fork: bool = False
    supports_native_skills: bool = False
    supports_native_agents: bool = False
    supports_programmatic_tools: bool = False
    supports_primary_launch: bool = False
    reference_input_mode: Literal["inline", "paths"] = "paths"
```

```python
class RunPromptPolicy(BaseModel):
    """Adapter-owned policy for composing one run prompt."""

    model_config = ConfigDict(frozen=True)

    include_agent_body: bool = True
    include_skills: bool = True
    skill_injection_mode: Literal["none", "append-system-prompt"] = "none"
```

```python
class SpawnParams(BaseModel):
    """Inputs required to launch one harness run."""

    model_config = ConfigDict(frozen=True)

    prompt: str
    model: ModelId | None = None
    effort: str | None = None
    skills: tuple[str, ...] = ()
    agent: str | None = None
    adhoc_agent_payload: str = ""
    extra_args: tuple[str, ...] = ()
    repo_root: str | None = None
    mcp_tools: tuple[str, ...] = ()
    interactive: bool = False
    continue_harness_session_id: str | None = None
    continue_fork: bool = False
    appended_system_prompt: str | None = None
    report_output_path: str | None = None
```

And the subprocess harness protocol in [adapter.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/adapter.py#L122) is:

```python
class SubprocessHarness(Protocol):
    """Protocol for subprocess-launching harness behavior."""

    @property
    def id(self) -> HarnessId: ...

    @property
    def capabilities(self) -> HarnessCapabilities: ...

    def run_prompt_policy(self) -> RunPromptPolicy: ...

    def build_adhoc_agent_payload(self, *, name: str, description: str, prompt: str) -> str: ...

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]: ...

    def mcp_config(self, run: SpawnParams) -> McpConfig | None: ...

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]: ...

    def blocked_child_env_vars(self) -> frozenset[str]: ...

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage: ...

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None: ...

    def resolve_session_file(self, *, repo_root: Path, session_id: str) -> Path | None: ...

    def seed_session(... ) -> SessionSeed: ...

    def filter_launch_content(... ) -> PromptPolicy: ...

    def detect_primary_session_id(... ) -> str | None: ...

    def owns_untracked_session(self, *, repo_root: Path, session_ref: str) -> bool: ...
```

This contract is good for:

- one prompt
- one command
- one child process
- optional post-run session-id extraction
- optional post-run report extraction

It is not a good base for:

- an open subprocess kept alive for many turns
- bidirectional turn injection
- runtime tool approval gating
- reconnecting to a live transport
- streaming deltas as normalized Meridian events

**1. Existing Harness Adapter Pattern**
Files under [src/meridian/lib/harness](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness):

- `__init__.py`
- `adapter.py`
- `claude.py`
- `codex.py`
- `common.py`
- `direct.py`
- `launch_types.py`
- `opencode.py`
- `registry.py`
- `session_detection.py`
- `transcript.py`

The registry in [registry.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/registry.py#L1) only knows two families: subprocess and in-process.

```python
@classmethod
def with_defaults(cls) -> Self:
    from meridian.lib.harness.claude import ClaudeAdapter
    from meridian.lib.harness.codex import CodexAdapter
    from meridian.lib.harness.direct import DirectAdapter
    from meridian.lib.harness.opencode import OpenCodeAdapter

    registry = cls()
    registry.register(ClaudeAdapter())
    registry.register(CodexAdapter())
    registry.register(OpenCodeAdapter())
    registry.register(DirectAdapter())
    return registry
```

There is no “persistent session harness” family today.

The shared command builder in [common.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/common.py#L549) is strict and single-shot:

```python
def build_harness_command(
    *,
    base_command: tuple[str, ...],
    subcommand: tuple[str, ...] = (),
    prompt_mode: PromptMode,
    run: SpawnParams,
    strategies: StrategyMap,
    perms: PermissionResolver,
    harness_id: HarnessId,
    mcp_config: McpConfig | None = None,
) -> list[str]:
```

It enforces that every `SpawnParams` field is either mapped or explicitly skipped:

```python
all_fields = set(SpawnParams.model_fields)
unmapped = all_fields - set(strategies.keys()) - _SKIP_FIELDS
if unmapped:
    raise ValueError(
        f"SpawnParams fields missing strategy mappings: {', '.join(sorted(unmapped))}. "
        f"Add a FlagStrategy (use DROP to ignore) for each."
    )
```

That is exactly the right tool for “turn params become one CLI argv”, and the wrong tool for “keep a session transport open and send many later turns”.

**Claude**
Claude is in [claude.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/claude.py).

Important constants:

- `BASE_COMMAND = ("claude", "-p", "--output-format", "stream-json", "--verbose")` at [claude.py:225](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/claude.py#L225)
- `PRIMARY_BASE_COMMAND = ("claude",)` at [claude.py:232](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/claude.py#L232)

Claude’s run prompt policy is the most specialized of the three subprocess adapters:

```python
def run_prompt_policy(self) -> RunPromptPolicy:
    return RunPromptPolicy(
        include_agent_body=False,
        include_skills=False,
        skill_injection_mode="append-system-prompt",
    )
```

Claude command building in [claude.py:261](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/claude.py#L261):

```python
def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
    if run.interactive:
        base_command = self.PRIMARY_BASE_COMMAND
        command_run = run.model_copy(update={"prompt": ""})
    else:
        base_command = self.BASE_COMMAND
        command_run = run.model_copy(update={"prompt": "-"})
    command = build_harness_command(...)
    if run.appended_system_prompt:
        command.extend(["--append-system-prompt", run.appended_system_prompt])
    adhoc_payload = run.adhoc_agent_payload.strip()
    if adhoc_payload:
        command.extend(["--agents", adhoc_payload])
    harness_session_id = (run.continue_harness_session_id or "").strip()
    if not harness_session_id:
        return command
    command.extend(["--resume", harness_session_id])
    if run.continue_fork:
        command.append("--fork-session")
    return command
```

What Claude does differently:

- child spawn uses `claude -p --output-format stream-json --verbose`
- prompt is fed on stdin via `-`
- skills are not inlined into the prompt
- skills go through `--append-system-prompt`
- agent profile body can go through `--agents` as an ad-hoc JSON payload
- resume/fork is native CLI behavior
- `CLAUDECODE` is blocked in child env so Meridian owns nesting

Claude session seeding in [claude.py:354](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/claude.py#L354):

```python
def seed_session(... ) -> SessionSeed:
    normalized_harness_session_id = harness_session_id.strip()
    if normalized_harness_session_id:
        return SessionSeed(session_id=normalized_harness_session_id)

    passthrough_session_id = _extract_passthrough_session_id(passthrough_args)
    if passthrough_session_id:
        return SessionSeed(session_id=passthrough_session_id)

    session_id = str(uuid4())
    return SessionSeed(
        session_id=session_id,
        session_args=("--session-id", session_id),
    )
```

Claude launch filtering in [claude.py:379](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/claude.py#L379):

```python
def filter_launch_content(... ) -> PromptPolicy:
    if is_resume:
        return PromptPolicy(skill_injection=skill_injection)
    # Claude does not currently expand profile skills via --agent
    # (see anthropics/claude-code#29902), so we must inject skill content
    # explicitly through Meridian's --append-system-prompt path.
    return PromptPolicy(prompt=prompt, skill_injection=skill_injection)
```

Claude also implements:

- `resolve_session_file(...)` at [claude.py:405](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/claude.py#L405)
- `detect_primary_session_id(...)` at [claude.py:395](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/claude.py#L395)
- `extract_conversation(...)` in the same file

Meaning: Claude already has the strongest native transcript/session discovery path, but Meridian still treats each launched Claude process as a one-run worker.

**Codex**
Codex is in [codex.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/codex.py).

Important constants:

- `BASE_COMMAND = ("codex", "exec", "--json")` at [codex.py:291](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/codex.py#L291)
- `PRIMARY_BASE_COMMAND = ("codex",)` at [codex.py:292](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/codex.py#L292)

Codex keeps the default prompt policy:

```python
def run_prompt_policy(self) -> RunPromptPolicy:
    return RunPromptPolicy()
```

So child-spawn prompt composition keeps agent body and skills inline by default.

Codex command building in [codex.py:327](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/codex.py#L327):

```python
def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
    harness_session_id = (run.continue_harness_session_id or "").strip()
    if run.interactive:
        guarded_prompt = run.prompt
        if guarded_prompt and not harness_session_id:
            guarded_prompt = f"{guarded_prompt}\n\nDO NOT DO ANYTHING. WAIT FOR USER INPUT."
        command_run = ...
        base_command = self.PRIMARY_BASE_COMMAND
        subcommand = ("resume", harness_session_id) if harness_session_id else ()
    else:
        command_run = run.model_copy(update={"prompt": "-"})
        if run.report_output_path:
            command_run = command_run.model_copy(
                update={
                    "extra_args": (*command_run.extra_args, "-o", run.report_output_path),
                },
            )
        base_command = self.BASE_COMMAND
        subcommand = ("resume", harness_session_id) if harness_session_id else ()
    return build_harness_command(...)
```

What Codex does differently:

- child spawn is `codex exec --json`
- prompt is fed via stdin
- child spawn can write final response directly to `report.md` via `-o`
- interactive primary launch uses `codex` or `codex resume <id>`
- fresh interactive primary launch gets the guard sentence because Codex has no true system prompt channel

Codex launch filtering in [codex.py:378](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/codex.py#L378):

```python
def filter_launch_content(... ) -> PromptPolicy:
    if is_resume:
        return PromptPolicy()
    return PromptPolicy(
        prompt=_compose_inline_launch_prompt(prompt=prompt, skill_injection=skill_injection),
        skill_injection="",
    )
```

This is a strong hint for future design: Codex needs prompt flattening for bootstrap, but that does not imply you want to flatten agent+skills into every later live turn.

Codex has the richest existing persistence clues:

- `resolve_session_file(...)` at [codex.py:405](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/codex.py#L405)
- `extract_session_id(...)` at [codex.py:431](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/codex.py#L431)
- fork logic that manipulates `~/.codex/state_5.sqlite` and rollout files
- `owns_untracked_session(...)` at [codex.py:507](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/codex.py#L507)

That makes Codex the best existing substrate for a future persistent-session adapter, but the current transport is still one `codex exec` per run.

**OpenCode**
OpenCode is in [opencode.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/opencode.py).

Important constants:

- `BASE_COMMAND = ("opencode", "run")` at [opencode.py:153](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/opencode.py#L153)
- `PRIMARY_BASE_COMMAND = ("opencode",)` at [opencode.py:154](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/opencode.py#L154)

OpenCode also keeps the default prompt policy.

OpenCode command building in [opencode.py:186](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/opencode.py#L186):

```python
def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
    base_command = self.PRIMARY_BASE_COMMAND if run.interactive else self.BASE_COMMAND
    command_run = run if run.interactive else run.model_copy(update={"prompt": "-"})
    command = build_harness_command(...)
    harness_session_id = (run.continue_harness_session_id or "").strip()
    if not harness_session_id:
        return command
    command.extend(["--session", harness_session_id])
    if run.continue_fork:
        command.append("--fork")
    return command
```

OpenCode-specific behavior:

- child spawn is `opencode run`
- prompt is fed via stdin
- resume/fork is `--session` plus optional `--fork`
- permissions can be passed via `OPENCODE_PERMISSION`
- session ownership is inferred by log scanning
- there is no `resolve_session_file(...)`

OpenCode env override in [opencode.py:208](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/opencode.py#L208):

```python
def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
    if config.opencode_permission_override:
        return {"OPENCODE_PERMISSION": config.opencode_permission_override}
    return {}
```

Important non-finding: there is no OpenCode HTTP or WebSocket backend in this repo. If the new design assumes that, that part is fresh work.

**Direct**
Direct mode is in [direct.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/direct.py). It is in-process and Anthropic-specific.

Capabilities in [direct.py:62](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/direct.py#L62):

```python
@property
def capabilities(self) -> HarnessCapabilities:
    return HarnessCapabilities(
        supports_stream_events=False,
        supports_session_resume=False,
        supports_native_skills=False,
        supports_programmatic_tools=True,
    )
```

The execution loop in [direct.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/direct.py#L140) is already multi-round:

```python
async def execute(... ) -> SpawnResult:
    messages: list[dict[str, object]] = [{"role": "user", "content": prompt}]
    final_usage = TokenUsage()
    final_response: dict[str, object] | None = None

    for _ in range(max_tool_round_trips):
        response = await asyncio.to_thread(self._request_messages, ...)
        ...
        messages.append({"role": "assistant", "content": content})
        tool_uses = [
            block
            for block in content
            if isinstance(block, dict) and block.get("type") == "tool_use"
        ]

        if not tool_uses:
            output = _extract_text_blocks(content)
            return SpawnResult(...)
        ...
        messages.append({"role": "user", "content": tool_results})
```

This is the only existing code that already models a dialogue loop inside Meridian. But it is not a reusable session backend because it has no persistent session ids, no harness transcript integration, no live reconnect behavior, and no session-store integration.

**2. Command Building and Spawn Invocation**
Child spawn CLI entry is [src/meridian/cli/spawn.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/cli/spawn.py).

It normalizes the main spawn-facing flags:

- `--agent/-a`
- `--prompt/-p`
- `--skills`
- `--approval`
- `--sandbox`
- `--effort`
- `--continue`
- `--fork`
- `--from`
- `--file`
- `--timeout`
- `--background`

Fresh child creation goes through `spawn_create_sync(...)` in [api.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/spawn/api.py#L74).

Preparation is in `build_create_payload(...)` in [prepare.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/spawn/prepare.py#L169). That resolves:

- runtime/config view
- requested/default agent
- model
- harness
- skill set
- continuation/fork session
- permission config
- composed prompt
- passthrough args
- preview command

The important policy-resolution center is [resolve.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/resolve.py#L220).

Key comment:

```python
# Two-pass resolution is required because selecting an agent determines
# profile overrides, while profile overrides participate in final layer
# resolution for model/harness/safety fields.
```

Key harness resolution logic:

```python
# Harness cannot live purely in the layer stack:
# 1) explicit layer harness wins
# 2) otherwise derive from resolved model
# 3) otherwise use configured default harness fallback
if resolved.harness:
    harness_id = HarnessId(resolved.harness)
elif resolved.model:
    harness_id = _derive_harness_from_model(resolved.model, repo_root=repo_root)
else:
    harness_id = HarnessId(configured_default_harness or 'claude')
```

And the per-field precedence fix:

```python
if resolved.model and model_set_in_pre_profile_layers and harness_from_profile_or_config:
    model_derived_harness = _derive_harness_from_model(resolved.model, repo_root=repo_root)
    if harness_id != model_derived_harness:
        harness_id = model_derived_harness
```

That directly implements the repo rule that a CLI/env model override should also drive derived harness selection.

The actual harness subprocess is launched in [runner.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/runner.py#L339), not in the CLI layer:

```python
async def spawn_and_stream(... ) -> SpawnResult:
    if not command:
        raise ValueError("Cannot spawn process: command is empty.")

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        env=env,
        start_new_session=True,
```

Important distinction:

- the harness itself is launched with `asyncio.create_subprocess_exec(...)`
- `subprocess.Popen(...)` elsewhere is for the detached Meridian background wrapper, not the actual harness transport

The single-run wrapper is [execute_with_finalization](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/runner.py#L632):

```python
async def execute_with_finalization(... ) -> int:
    """Execute one run and always append a finalize row via try/finally."""
```

That is the current single-shot lifecycle boundary.

**Single-Shot Lifecycle**
Today’s child-spawn lifecycle is:

1. CLI parses flags in [spawn.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/cli/spawn.py).
2. `spawn_create_sync(...)` in [api.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/spawn/api.py#L74) is called.
3. `build_create_payload(...)` in [prepare.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/spawn/prepare.py#L169) resolves policies, skills, prompt, permissions, and continuation.
4. spawn `start` is appended to `spawns.jsonl`.
5. `params.json` and `prompt.md` are materialized.
6. the actual harness process is launched in [runner.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/runner.py#L339).
7. stdout/stderr are captured, usage/session/report are extracted.
8. a final `finalize` event is appended.

That lifecycle is completion-oriented at every layer.

**The Biggest Single-Shot Transport Blockers**
stdin is written once and then closed in [runner.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/runner.py#L446):

```python
if stdin_text is not None:
    if process.stdin is None:
        raise RuntimeError("Subprocess did not expose stdin pipe.")

    async def _feed_stdin() -> None:
        assert process.stdin is not None
        try:
            process.stdin.write(stdin_text.encode("utf-8"))
            await process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            process.stdin.close()
            with suppress(BrokenPipeError, ConnectionResetError):
                await process.stdin.wait_closed()
```

The report watchdog in [runner.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/runner.py#L320) treats “report exists but process still alive” as abnormal:

```python
if process.returncode is None:
    logger.info(
        "Report watchdog: harness wrote report but process still alive "
        "after %.0fs grace. Terminating.",
        grace_secs,
    )
    await terminate_process(process, grace_seconds=10.0)
    return True
```

For a persistent session backend, both behaviors are wrong by design.

**3. Profile + Skill Loading**
Agent profile parsing is in [catalog/agent.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/catalog/agent.py#L73).

Relevant entry points:

- `parse_agent_profile(path: Path) -> AgentProfile` at line 73
- `load_agent_profile(...)` at line 197

Profiles are read from `.agents/agents/*.md`.

Skills are read from `.agents/skills/**/SKILL.md` by [catalog/skill.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/catalog/skill.py#L128), with `SkillRegistry` as the filesystem-backed registry.

Skill resolution for a run happens in [resolve.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/resolve.py#L73) via `resolve_skills_from_profile(...)`. That merges:

- profile-declared skills
- explicit requested skills
- installed skill content on disk
- warnings for missing skills

Prompt assembly is in [prompt.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/prompt.py#L183) and [prompt.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/prompt.py#L243).

The report instruction is hardcoded in [prompt.py:102](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/prompt.py#L102):

```python
def build_report_instruction() -> str:
    """Build the report instruction appended to each composed run prompt."""

    return (
        "# Report\n\n"
        "**IMPORTANT - As your final action, create the run report with Meridian.**\n\n"
        "Run `meridian spawn report create --stdin` and provide a plain markdown report "
        "via stdin.\n\n"
        "Include: what was done, key decisions made, files created/modified, "
        "verification results, and any issues or blockers.\n\n"
        "If `meridian spawn report create` is unavailable or fails, provide the same markdown "
        "as your final assistant message so fallback extraction can persist the report."
    )
```

Skill injection for the Claude-style system-prompt lane is separate in [prompt.py:139](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/prompt.py#L139):

```python
def compose_skill_injections(skills: Sequence[SkillContent]) -> str | None:
    """Format skill content for --append-system-prompt injection."""
    ...
    blocks.append(f"# Skill: {skill.path}\n\n{content}")
```

The data flow into a Claude child spawn is:

1. resolve profile + skills
2. ask Claude adapter for `RunPromptPolicy`
3. omit agent body and skills from main run prompt
4. create appended skill payload via `compose_skill_injections(...)`
5. create ad-hoc agent JSON via `build_adhoc_agent_payload(...)`
6. feed:
   - prompt on stdin
   - skills via `--append-system-prompt`
   - profile body via `--agents`

So the “CLAUDE.md equivalent” for Claude is split across multiple transport lanes. There is no single assembled file.

For Codex and OpenCode child spawns, the default prompt policy leaves agent body + skills inline in the main composed prompt.

For Codex primary launches, the system-prompt gap is handled by prompt flattening, not by a separate system channel.

That means prompt/bootstrap composition is already harness-specific and reusable, but a future long-lived design should split bootstrap from later turn injection rather than replay the whole bootstrap prompt every turn.

**4. Approval Modes Mapping**
Permissions live in [permissions.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/safety/permissions.py#L17).

Resolved config:

```python
class PermissionConfig(BaseModel):
    """Resolved permission configuration for one run."""

    model_config = ConfigDict(frozen=True)

    sandbox: str | None = None
    approval: str = "default"
    opencode_permission_override: str | None = None
```

Mapping to harness-specific flags is in `permission_flags_for_harness(...)`.

Current mapping:

- `yolo`
- Claude => `--dangerously-skip-permissions`
- Codex => `--dangerously-bypass-approvals-and-sandbox`
- OpenCode => no global bypass flag

- `auto`
- Claude => `--permission-mode acceptEdits`
- Codex => `--full-auto`

- `confirm`
- Claude => `--permission-mode default`
- Codex => `--ask-for-approval untrusted`

- `default`
- no explicit approval flags

Sandbox mapping today is Codex-only:

```python
if sandbox is None:
    return []

if harness_id == HarnessId.CODEX:
    return ["--sandbox", sandbox]

# Other harnesses: no sandbox flag support yet.
return []
```

OpenCode has an extra env-based path:

- `OPENCODE_PERMISSION` derived from allowed/disallowed tool lists

Design implication: this module is reusable for meaning, but not sufficient for runtime approval gating. A live session adapter will need a second abstraction layer that turns Meridian approval semantics into active “tool approval requested / resolved” events.

**5. State + File Layout**
The state root model is in [paths.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/paths.py#L1).

`StateRootPaths` includes:

- `spawns.jsonl`
- `spawns.jsonl.flock`
- `sessions.jsonl`
- `sessions.jsonl.flock`
- `session-id-counter`
- `sessions/`
- `fs/`
- `work/`
- `work-archive/`
- `spawns/`

`resolve_state_paths(...)` additionally exposes:

- `.meridian/artifacts`
- `.meridian/cache`
- `.meridian/config.toml`

Important nuance: there are two relevant spawn-related locations today.

- `.meridian/spawns/<spawn_id>/...`
- `.meridian/artifacts/<spawn_id>/...`

That split will matter for persistent-session design. The current code already separates user-facing logs from generic artifact store data.

Crash-safe writes are in [atomic.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/atomic.py#L23). It uses temp-file + `fsync` + `os.replace` + parent-dir `fsync`.

Append-only event writes and locking are in [event_store.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/event_store.py#L63). It uses `fcntl.flock`, and reads tolerate malformed/truncated JSONL lines.

Spawn projection is in [spawn_store.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/spawn_store.py#L171). The core event types are:

- `start`
- `update`
- `finalize`

That is strongly terminal-state-oriented.

Session projection is in [session_store.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/session_store.py#L311).

Relevant entry points:

- `start_session(...)`
- `stop_session(...)`
- `update_session_harness_id(...)`

Session records already track both Meridian `chat_id` and harness-native `harness_session_id`. That is the best existing persistence primitive for a future persistent session design.

But the scope manager in [session_scope.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/session_scope.py#L24) is explicitly short-lived:

```python
def session_scope(... ) -> Iterator[ManagedSession]:
    resolved_chat_id = _start_session(...)
    ...
    try:
        yield ManagedSession(...)
    finally:
        _stop_session(state_root, resolved_chat_id)
```

So a current “session” is usually “session for this run”, not “active long-lived transport”.

Reconciliation in [reaper.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/reaper.py) checks:

- `background.pid`
- `harness.pid`
- `heartbeat`
- `output.jsonl`
- `stderr.log`
- `report.md`

That logic is reusable, but it assumes a finite run that eventually becomes terminal.

**6. Extension Points for a New Long-Lived Session Adapter**
Strong reuse candidates:

- [resolve.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/resolve.py)
- [catalog/agent.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/catalog/agent.py)
- [catalog/skill.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/catalog/skill.py)
- [prompt.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/prompt.py)
- [reference.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/reference.py)
- [permissions.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/safety/permissions.py)
- [atomic.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/atomic.py)
- [event_store.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/event_store.py)
- [session_store.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/session_store.py)
- [transcript.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/transcript.py)
- [launch/env.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/env.py)

Likely extension points:

- [registry.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/registry.py)
- [session_store.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/session_store.py)
- [spawn_store.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/spawn_store.py)
- [ops/session_log.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/session_log.py)
- [ops/reference.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/reference.py)
- [session_scope.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/session_scope.py)

What I would write fresh:

- `src/meridian/lib/harness/session/adapter.py`
- `src/meridian/lib/harness/session/registry.py`
- `src/meridian/lib/harness/session/events.py`
- `src/meridian/lib/harness/session/runner.py`
- `src/meridian/lib/harness/session/approval.py`
- `src/meridian/lib/harness/session/claude.py`
- `src/meridian/lib/harness/session/codex.py`
- `src/meridian/lib/harness/session/opencode.py`
- likely a new `src/meridian/lib/ops/live_session/` package

I would not overload `SubprocessHarness` to handle persistent transport. Reuse its naming ideas and some DTO concepts, but not the protocol itself.

Why not:

- `build_command(...)` assumes one launch command
- `extract_usage(...)` is post-run
- `extract_session_id(...)` is post-launch/post-run
- `extract_report(...)` assumes one final artifact
- `seed_session(...)` is launch-time only
- `filter_launch_content(...)` is launch-time only
- there is no `send_turn(...)`
- there is no `stream_events(...)`
- there is no `approve_tool(...)`
- there is no `interrupt_turn(...)`
- there is no `reconnect(...)`

The clean split is a sibling abstraction family, not a mutation of the current subprocess one.

**7. Gotchas / Friction Points**
Main pain points if you try to retrofit long-lived sessions into the current single-shot path:

- `spawn_and_stream(...)` writes stdin once and closes it
- `execute_with_finalization(...)` always ends in `finalize`
- `report.md` means “final response for this run”
- report watchdog terminates a process that remains alive after writing a report
- `session_scope(...)` always stops the session in `finally`
- background worker model assumes one finite job
- `SpawnRecord` is one-run-centric
- approval handling is launch-time only
- there is no normalized live event schema
- transcript handling is largely post-hoc, file-based parsing
- OpenCode has weaker transcript continuity because it lacks `resolve_session_file(...)`
- all subprocess adapters currently return `None` from `mcp_config(...)`
- Codex forking is already special-cased in multiple places
- Claude has CWD/process-lifecycle quirks that already needed workarounds in [runner.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/runner.py)

One especially important friction point: `supports_stream_events=True` exists in capabilities, but the rest of the system does not yet treat live stream events as a first-class harness contract. That is a clue that the current layer is only halfway toward a proper live-session abstraction.

**8. How Codex Exec vs Claude Stream-JSON vs OpenCode Is Treated Today**
Claude today:

- launched as `claude -p --output-format stream-json --verbose`
- stdout can be event-like
- resume/fork exists
- transcript/session-file resolution exists
- still treated as a one-run process

Codex today:

- launched as `codex exec --json`
- session ids are durable enough for file discovery and forking
- resume is CLI-native
- native transcript files exist under `~/.codex/sessions`
- still treated as one subprocess per turn

OpenCode today:

- launched as `opencode run`
- session id can be resumed/forked via CLI flags
- permission override has env-based shaping
- session discovery relies on logs
- no in-repo HTTP/WebSocket backend exists

Direct today:

- only existing in-process dialogue loop
- useful conceptual precedent for “conversation loop inside Meridian”
- not integrated with the session/transcript/store model needed for a persistent harness transport

**Recommendation**
Recommended shape:

- keep `SubprocessHarness` unchanged for one-shot runs
- add a sibling `SessionHarness` family under `src/meridian/lib/harness/session/`
- reuse current policy/profile/skill/prompt/state primitives for bootstrap and persistence
- create a new live-session runtime instead of extending `execute_with_finalization(...)`

The most reusable existing pieces are:

- policy resolution
- profile loading
- skill loading
- bootstrap prompt composition
- permission semantics
- file-authoritative session identity/state
- transcript parsing

The part that is missing is the actual live transport abstraction.

My recommended normalized live event model would include:

- `session.started`
- `session.reconnected`
- `session.heartbeat`
- `turn.started`
- `assistant.delta`
- `assistant.completed`
- `tool.approval_requested`
- `tool.approval_resolved`
- `tool.started`
- `tool.completed`
- `turn.failed`
- `turn.completed`
- `session.closed`

And I would separate:

- bootstrap prompt composition
- incremental user-turn composition
- approval-gating flow
- transcript replay
- final report emission

**Verification**
I verified this by reading:

- [src/meridian/lib/harness/adapter.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/adapter.py)
- [src/meridian/lib/harness/claude.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/claude.py)
- [src/meridian/lib/harness/codex.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/codex.py)
- [src/meridian/lib/harness/opencode.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/opencode.py)
- [src/meridian/lib/harness/direct.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/direct.py)
- [src/meridian/lib/harness/common.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/common.py)
- [src/meridian/lib/harness/registry.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/registry.py)
- [src/meridian/lib/ops/spawn/api.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/spawn/api.py)
- [src/meridian/lib/ops/spawn/prepare.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/spawn/prepare.py)
- [src/meridian/lib/launch/resolve.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/resolve.py)
- [src/meridian/lib/launch/prompt.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/prompt.py)
- [src/meridian/lib/launch/runner.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/runner.py)
- [src/meridian/lib/launch/session_scope.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/session_scope.py)
- [src/meridian/lib/safety/permissions.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/safety/permissions.py)
- [src/meridian/lib/state/paths.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/paths.py)
- [src/meridian/lib/state/atomic.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/atomic.py)
- [src/meridian/lib/state/event_store.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/event_store.py)
- [src/meridian/lib/state/spawn_store.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/spawn_store.py)
- [src/meridian/lib/state/session_store.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/session_store.py)
- [src/meridian/lib/state/reaper.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/state/reaper.py)
- [src/meridian/lib/ops/session_log.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/ops/session_log.py)
- [src/meridian/lib/harness/transcript.py](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/harness/transcript.py)

I also verified the report command shape from the CLI:

- `meridian report create --help` is invalid
- `meridian spawn report create --help` is valid

That matches [prompt.py:102](/home/jimyao/gitrepos/meridian-channel/src/meridian/lib/launch/prompt.py#L102) and means the stale `meridian report create --stdin` wording in the task prompt is outdated relative to the codebase.

No files changed.
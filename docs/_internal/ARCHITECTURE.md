# Architecture

Meridian is a coordination layer for multi-agent systems. It launches, tracks, and inspects AI agent spawns across multiple harnesses (Claude, Codex, OpenCode, direct API). It is not a filesystem, execution engine, or data warehouse.

## System Overview

```mermaid
graph TD
    User["User / Parent Agent"] --> CLI["CLI (cyclopts)<br/>cli/main.py"]
    User --> MCP["MCP Server (FastMCP)<br/>server/main.py"]

    CLI --> Ops["Feature Handlers<br/>ops/"]
    MCP --> Ops

    Ops --> Launch["Launch Lifecycle<br/>launch/"]
    Ops --> Catalog["Catalog<br/>catalog/"]

    Launch --> Harness["Harness Adapters<br/>harness/"]
    Launch --> State["State Stores<br/>state/"]
    Launch --> Safety["Safety<br/>safety/"]

    Harness --> Claude["ClaudeAdapter"]
    Harness --> Codex["CodexAdapter"]
    Harness --> OC["OpenCodeAdapter"]
    Harness --> Direct["DirectAdapter"]

    State --> FS[".meridian/"]
```

## Dependency Model

```mermaid
graph TD
    Surfaces["Surfaces<br/>cli/, server/, harness/direct.py"] --> Handlers["Feature Handlers<br/>ops/spawn/, ops/config.py, ops/catalog.py, ..."]
    Handlers --> Launch["Launch Lifecycle<br/>launch/"]
    Launch --> Infra["Shared Infrastructure<br/>harness/ + safety/, state/, catalog/, config/"]
    Infra --> Core["Core Primitives<br/>core/"]
```

Rules:
- **Surfaces** depend on ops and core. They contain no business logic.
- **Feature handlers** depend on launch, infrastructure, and core.
- **Launch** depends on harness adapters, state stores, safety, and core.
- **Infrastructure** packages (including safety) do not import surfaces or ops.
- **Core** imports nothing from the rest of the codebase.

---

## Core Concepts

### State Root

A repo-local coordination root under `.meridian/`. It contains shared filesystem state, spawn history, session history, and per-spawn artifacts for one Meridian-managed workspace.

### Spawn

A single agent execution within the repo's `.meridian/` state root. Spawns are launched via `meridian spawn`, tracked via JSONL events, and can be nested (a spawn can create child spawns).

### Harness

An AI backend adapter. The same `meridian spawn` command works across Claude, Codex, and OpenCode. Each harness translates spawn parameters into the native CLI invocation for that backend.

### Agent Profile

A YAML-frontmatter markdown file (`.agents/agents/NAME.md`) defining an agent's capabilities: model, skills, sandbox permissions, MCP tools, and system prompt body.

### Skill

Domain knowledge loaded into an agent at launch time. Skills survive context compaction because they are injected fresh on every launch/resume. Defined as `SKILL.md` files under `.agents/skills/SKILLNAME/`.

---

## Directory Layout

```
src/meridian/
  cli/                         # Cyclopts surface -- thin dispatch, no business logic
    main.py                    # Entry point, global options, command dispatch
    spawn.py                   # Spawn subcommand handlers
    output.py                  # Output sink implementations (text/JSON/agent)
    format_helpers.py          # Tabular display formatting
    config_cmd.py              # Config subcommands
    report_cmd.py              # Report subcommands
    skills_cmd.py              # Skills subcommands
    models_cmd.py              # Models subcommands
    doctor_cmd.py              # Doctor subcommand
    sync_cmd.py                # Sync subcommand

  server/
    main.py                    # FastMCP server on stdio

  lib/
    core/                      # Lightweight shared primitives (imports nothing else)
      types.py                 # NewType identifiers (SpawnId, HarnessId, ModelId, ArtifactKey)
      domain.py                # Frozen Pydantic domain models (Spawn, TokenUsage, SkillManifest, ...)
      context.py               # RuntimeContext (MERIDIAN_* env vars)
      sink.py                  # OutputSink protocol
      codec.py                 # Type schema serialization
      util.py                  # Serialization + formatting helpers
      logging.py               # Structlog configuration

    config/                    # Application settings only
      settings.py              # MeridianConfig (pydantic-settings, TOML + env)

    catalog/                   # "What's available?" -- discovery and parsing
      agent.py                 # Agent profile parsing (YAML frontmatter markdown)
      skill.py                 # Skill parsing + registry
      models.py                # Model aliases, discovery, routing, catalog

    harness/                   # Adapter protocol + implementations
      adapter.py               # HarnessAdapter protocol, SpawnParams, SpawnResult, HarnessCapabilities
      registry.py              # HarnessRegistry (model-to-adapter routing)
      claude.py                # Claude CLI adapter
      codex.py                 # Codex CLI adapter
      opencode.py              # OpenCode CLI adapter
      direct.py                # Direct Anthropic Messages API adapter
      common.py                # Shared adapter utilities + strategies
      materialize.py           # Agent/skill materialization into harness dirs
      launch_types.py          # PromptPolicy, SessionSeed (shared between harness + launch)
      session_detection.py     # Harness-specific session ID extraction

    state/                     # ALL file-backed stores
      paths.py                 # State path resolution + compatibility helpers
      spawn_store.py           # Spawn event store (JSONL) + ID generation
      session_store.py         # Session tracking (sessions.jsonl)
      artifact_store.py        # Artifact storage and retrieval

    safety/                    # Harness-facing safety translation (adapts + passes through)
      permissions.py           # PermissionTier -> harness CLI flags translation
      budget.py                # Cost tracking from harness JSONL output
      guardrails.py            # Post-run script hooks
      redaction.py             # Secret env var injection + output redaction

    launch/                    # Unified harness launch lifecycle
      __init__.py              # launch_primary() facade
      resolve.py               # Model/agent/harness resolution
      command.py               # Build harness CLI command
      process.py               # Run harness process (fork/exec + stream)
      types.py                 # Primary launch request/result models
      prompt.py                # Prompt assembly pipeline
      reference.py             # Reference file handling
      runner.py                # execute_with_finalization (spawn subprocess orchestration)
      extract.py               # Post-run token/session/report extraction
      report.py                # Report extraction logic
      written_files.py         # Explicit written-file metadata extraction
      artifact_io.py           # Artifact I/O helpers
      signals.py               # Signal forwarding (SIGINT/SIGTERM) + process groups
      env.py                   # Child process environment (MERIDIAN_* vars)
      errors.py                # Error classification + retry logic
      timeout.py               # Spawn timeout management (SIGTERM -> grace -> SIGKILL)
      terminal.py              # TTY detection

    ops/                       # Feature handlers -- business logic
      manifest.py              # Explicit operation manifest (replaces old registry)
      runtime.py               # OperationRuntime, resolve_runtime
      spawn/                   # Spawn feature package
        api.py                 # spawn_create, spawn_list, spawn_show, spawn_wait, spawn_cancel, spawn_continue, spawn_stats
        models.py              # Request/response models (SpawnCreateInput, SpawnActionOutput, ...)
        prepare.py             # Payload validation + launch prep
        execute.py             # Blocking/background execution
        query.py               # Show/list/reference resolution
      config.py                # Config TOML handlers (get, set, show, init, reset)
      catalog.py               # Models + skills query handlers
      report.py                # Report CRUD handlers (create, show, search)
      diag.py                  # Doctor diagnostics
```

---

## Data Flow: `meridian spawn create`

```mermaid
sequenceDiagram
    participant CLI as CLI / MCP
    participant Ops as ops/spawn/api.py
    participant Safety as Safety
    participant Harness as Harness Registry
    participant Store as State Store
    participant Launch as Launch Lifecycle
    participant Child as Child Process

    CLI->>Ops: spawn_create_sync

    rect rgba(128, 128, 128, 0.08)
        Note over Ops,Safety: Preparation
        Ops->>Ops: resolve_runtime
        Ops->>Safety: build_permission_config
        Ops->>Harness: route_model -> adapter
        Ops->>Ops: compose prompt + resolve agent
    end

    rect rgba(128, 128, 128, 0.08)
        Note over Store,Child: Execution
        Ops->>Store: start_spawn event (spawns.jsonl)
        Ops->>Harness: build_command (SpawnParams -> CLI args)
        Ops->>Launch: execute_with_finalization
        Launch->>Child: asyncio subprocess
        Child-->>Launch: stdout/stderr stream
        Launch->>Launch: parse_stream_event
    end

    rect rgba(128, 128, 128, 0.08)
        Note over Ops,Store: Finalization
        Launch->>Launch: extract tokens + session + report
        Ops->>Store: finalize_spawn event (spawns.jsonl)
    end

    Ops-->>CLI: SpawnActionOutput
```

## Data Flow: `meridian`

```mermaid
sequenceDiagram
    participant CLI as CLI
    participant LaunchFacade as CLI primary launch
    participant Launch as launch/
    participant Config as Config
    participant Harness as Harness
    participant Process as Harness Process

    CLI->>LaunchFacade: PrimaryLaunchRequest

    rect rgba(128, 128, 128, 0.08)
        Note over LaunchFacade,Harness: Resolution
        LaunchFacade->>Config: load_config
        LaunchFacade->>Launch: resolve_harness + resolve_primary_session
        LaunchFacade->>Harness: materialize agents/skills
        LaunchFacade->>Launch: build_harness_command
    end

    LaunchFacade->>Launch: run_harness_process
    Process-->>CLI: interactive I/O
    Process-->>LaunchFacade: PrimaryLaunchResult
```

---

## State Model

All state lives in files. No database. Append-only JSONL for event streams and per-spawn directories for artifacts. Atomic writes via `tmp` + `os.replace()`, concurrency via `fcntl.flock`.

```mermaid
graph TD
    Root[".meridian/"] --> Config["config.toml"]
    Root --> Models["models.toml"]
    Root --> Cache["cache/"]
    Root --> FS["fs/ (shared workspace)"]
    Root --> Work["work/"]
    Root --> SpJ["spawns.jsonl"]
    Root --> SeJ["sessions.jsonl"]
    Root --> SpDir["spawns/"]
    SpDir --> Sp1["&lt;spawn-id&gt;/"]
    Sp1 --> Out["output.jsonl"]
    Sp1 --> Err["stderr.log"]
    Sp1 --> Tok["tokens.json"]
    Sp1 --> Rep["report.md"]
```

### Event Sourcing

Spawn lifecycle is tracked as append-only JSONL events in `spawns.jsonl`:

```json
{"v":1,"event":"start","id":"p1","chat_id":"c1","model":"claude-opus-4-6","harness":"claude","kind":"primary","status":"running","prompt":"...","started_at":"..."}
{"v":1,"event":"finalize","id":"p1","status":"succeeded","exit_code":0,"finished_at":"...","duration_secs":42.5}
```

Session lifecycle follows the same pattern in `sessions.jsonl` with `start`, `stop`, and `update` events. Both use Pydantic event models for typed serialization at I/O boundaries.

### ID Generation

- Spawn IDs: `p1, p2, ...` (counter from `spawns.jsonl`)
- Chat/Session IDs: `c1, c2, ...` (counter from `sessions.jsonl`)

---

## Harness System

The harness layer abstracts AI backend differences behind a common protocol.

```mermaid
graph TD
    Registry["HarnessRegistry<br/>route_model()"] --> CA["ClaudeAdapter"]
    Registry --> CX["CodexAdapter"]
    Registry --> OC["OpenCodeAdapter"]
    Registry --> DA["DirectAdapter"]

    CA --> Proto["HarnessAdapter Protocol"]
    CX --> Proto
    OC --> Proto
    DA --> Proto

    Proto --- BC["build_command()<br/>SpawnParams -> CLI args"]
    Proto --- PS["parse_stream_event()<br/>stdout line -> StreamEvent"]
    Proto --- EU["extract_usage()<br/>artifacts -> TokenUsage"]
    Proto --- SS["seed_session()<br/>resume/fork control"]
    Proto --- FC["filter_launch_content()<br/>prompt policy"]
```

Each adapter translates `SpawnParams` into native CLI args:
- **Claude**: `claude eval --json --model X --prompt Y`
- **Codex**: `codex exec --model X --prompt Y`
- **OpenCode**: `opencode --provider google --model X`
- **Direct**: In-process Anthropic Messages API (programmatic tools, no subprocess)

Routing rules (in `catalog/models.py`): `claude-*|sonnet*|opus*` to Claude, `gpt-*|codex*|o3*|o4*` to Codex, `gemini-*|opencode-*|/*` to OpenCode.

---

## Operation Manifest

All operations are defined in an explicit manifest (`ops/manifest.py`). Each entry declares metadata consumed by both CLI and MCP surfaces -- no import-time registration or global mutation.

```python
class OperationSpec:
    name: str                           # e.g. "spawn.create"
    description: str
    handler: async callable             # MCP / async callers
    sync_handler: sync callable | None  # CLI / sync callers
    input_type: type                    # Pydantic model
    output_type: type                   # Pydantic model
    cli_group: str | None               # e.g. "spawn"
    cli_name: str | None                # e.g. "create"
    mcp_name: str | None                # e.g. "spawn_create"
    surfaces: frozenset["cli","mcp"]    # which surfaces expose it
```

Surfaces consume the manifest via `get_operations_for_surface("cli"|"mcp")`. Some operations are surface-restricted (e.g., `spawn.create` is MCP-only, `config.*` is CLI-only).

---

## Configuration

Configuration uses pydantic-settings `BaseSettings` with layered precedence:

```
Defaults -> Project TOML (.meridian/config.toml) -> User TOML (~/.meridian/config.toml) -> Env Vars (MERIDIAN_*) -> CLI Flags
```

Key env vars:

| Variable | Purpose |
|----------|---------|
| `MERIDIAN_MODEL` | Default model |
| `MERIDIAN_HARNESS` | Default harness |
| `MERIDIAN_FS_DIR` | Shared filesystem path (`.meridian/fs`) |
| `MERIDIAN_SPAWN_ID` | Current spawn ID |
| `MERIDIAN_PARENT_SPAWN_ID` | Parent spawn ID |
| `MERIDIAN_DEPTH` | Nesting depth (0 = primary) |
| `MERIDIAN_REPO_ROOT` | Repository root path |
| `MERIDIAN_CHAT_ID` | Current session chat ID |

---

## Safety

Safety enforcement is delegated to the harnesses. Meridian's `safety/` package is harness adapter support code — it translates Meridian's abstractions into harness-native flags and passes them through.

- **permissions.py** — Translates three permission tiers (`read-only`, `workspace-write`, `full-access`) into harness-specific CLI flags (`--allowedTools` for Claude, `--sandbox` for Codex). The harness does the actual enforcement.
- **budget.py** — Parses cost fields from harness JSONL output during streaming. Terminates spawns that exceed configured USD limits. The only Meridian-side enforcement.
- **redaction.py** — Injects `--secret KEY=VALUE` as `MERIDIAN_SECRET_*` env vars into the harness child process and redacts values from streamed output.
- **guardrails.py** — Post-run script hooks (the one piece that isn't strictly harness adapter code).

---

## Launch Lifecycle

The `launch/` package owns the entire harness process lifecycle, unifying what was previously split across four separate packages:

```
resolve -> build prompt -> build command -> fork process -> stream output -> extract results -> finalize
```

```mermaid
graph TD
    Start["resolve.py<br/>model + harness + agent"] --> Prompt["prompt.py<br/>compose prompt + skills"]
    Prompt --> Command["command.py<br/>build CLI args"]
    Command --> Runner["runner.py<br/>execute_with_finalization"]
    Runner --> Subprocess["asyncio subprocess"]
    Subprocess --> Stream["parse_stream_event"]
    Subprocess --> Signals["signals.py<br/>SIGINT/SIGTERM forwarding"]
    Subprocess --> Timeout["timeout.py<br/>SIGTERM -> grace -> SIGKILL"]
    Stream --> Extract["extract.py<br/>tokens + session + report"]
    Extract --> Done["finalize_spawn event"]
```

Both primary agent launch (`meridian`) and spawn execution (`meridian spawn create`) use the same lifecycle.

---

## Spawn Nesting

Spawns can create child spawns. Each child inherits the shared `.meridian/fs/` context and receives incremented depth tracking.

```mermaid
graph TD
    Primary["Primary Agent<br/>depth=0"] --> S1["Spawn p1<br/>depth=1"]
    Primary --> S2["Spawn p2<br/>depth=1"]
    S1 --> S3["Spawn p3<br/>depth=2"]
    S1 --> S4["Spawn p4<br/>depth=2"]
```

Context propagation per child: `MERIDIAN_FS_DIR`, `MERIDIAN_SPAWN_ID`, `MERIDIAN_PARENT_SPAWN_ID`, `MERIDIAN_DEPTH` (parent + 1). The shared filesystem at `fs/` enables data passing between siblings and across depths. `max_depth` config prevents runaway recursion.

---

## Conventions

- All identifiers are `NewType` wrappers (`SpawnId`, `ModelId`, `HarnessId`, `ArtifactKey`) for compile-time safety
- All domain and I/O types are frozen Pydantic `BaseModel` instances
- State persistence uses `model_validate()` / `model_dump()` at I/O boundaries

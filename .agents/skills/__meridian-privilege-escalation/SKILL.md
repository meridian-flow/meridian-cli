---
name: __meridian-privilege-escalation
description: How to escalate agent permissions in meridian when a spawn hits capability limits — sandbox tiers, approval modes, model/harness switching, and per-spawn overrides. Use when a spawned agent fails because of sandbox restrictions, missing tools, harness limitations, or insufficient permissions, and you need to change the spawn configuration to unblock it.
---

# Privilege Escalation

Meridian agents run with constrained permissions by default — sandboxed filesystems, restricted tools, harness-specific limitations. When a spawn can't complete its task because of these constraints, you can escalate permissions per-spawn without changing the agent profile.

## Sandbox Tiers

The `--sandbox` flag controls filesystem and process access. Tiers from most to least restrictive:

| Tier | What it allows |
|---|---|
| `read-only` | Read files only. No writes, no process execution. |
| `workspace-write` | Read/write within the workspace. No network listeners, no access outside project. |
| `full-access` | Full filesystem and process access. Can bind ports, access network, write anywhere. |

Override per-spawn:
```bash
meridian spawn -a coder --sandbox full-access -p "Run integration tests that bind to localhost..."
```

Agent profiles set a default tier (e.g. `sandbox: workspace-write`). The `--sandbox` flag overrides it for that specific spawn only.

## Approval Modes

The `--approval` flag controls how the harness handles tool-call approvals:

| Mode | Behavior |
|---|---|
| `default` | Harness decides (each harness has its own default policy). |
| `confirm` | User approves each tool call. |
| `auto` | Auto-approve safe operations, prompt for dangerous ones. |
| `yolo` | Approve everything. No prompts. |

Override per-spawn:
```bash
meridian spawn -a coder --approval auto -p "..."
meridian spawn -a coder --approval yolo -p "..."   # use sparingly
```

## Model/Harness Switching

Different models route to different harnesses, and each harness has different capability profiles. Switching the model can bypass harness-level restrictions entirely:

```bash
# Codex harness has a sandbox that restricts network binding
meridian spawn -a coder -m codex -p "..."

# Claude harness has no sandbox — switching model sidesteps the restriction
meridian spawn -a coder -m opus -p "..."
```

Run `meridian models list` to see which models route to which harness.

## Common Escalation Scenarios

**"Can't bind to a port / start a server"** — sandbox restricts network listeners.
→ `--sandbox full-access` or switch to a harness without sandbox restrictions (`-m opus`).

**"Can't write files outside workspace"** — sandbox restricts filesystem scope.
→ `--sandbox full-access` for the specific spawn that needs it.

**"Can't access the network / fetch URLs"** — harness or sandbox restriction.
→ Use an agent with WebFetch/WebSearch tools (e.g. `researcher`), or escalate sandbox.

**"Permission denied on tool call"** — approval mode is blocking.
→ `--approval auto` or `--approval yolo` for that spawn.

**"Context too small for the task"** — model limitation.
→ Switch to a model with a larger context window (`-m gemini` for large context).

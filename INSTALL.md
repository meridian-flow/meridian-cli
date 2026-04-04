# Meridian Install Guide for LLM Agents

Use this guide when the user asks you to install and set up `meridian-channel`.
Execute commands exactly, ask the user at decision points, and report command output succinctly.

## Step 0: Prerequisites

1. Check whether `uv` is installed:

```bash
which uv
```

2. If `uv` is missing, install it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Check Python version:

```bash
python3 --version
```

4. Confirm Python is `3.12` or newer. If not, ask the user to upgrade Python before continuing.

## Step 1: Install Meridian

Run the recommended install:

```bash
uv tool install meridian-channel
```

From source (for development or pre-release):

```bash
git clone https://github.com/haowjy/meridian-channel.git
cd meridian-channel
uv tool install --force . --no-cache --reinstall
```

Verify the CLI is available:

```bash
meridian --help
```

## Step 2: Initialize Project

In the user's project root, run:

```bash
meridian config init
```

This creates `.meridian/` with baseline config.

## Step 3: Install Agent & Skill Packages

Ask the user: `Would you like to install the dev workflow agents and skills? This gives you a full dev team — coder, reviewers, testers, researcher, documenter — with structured workflow skills.`

Initialize mars config in the project:

```bash
meridian mars init
```

If yes, add the dev workflow package:

```bash
meridian mars add @haowjy/meridian-dev-workflow
```

If they only want the core coordination primitives (without the dev team), add base only:

```bash
meridian mars add @haowjy/meridian-base
```

Sync packages into `.agents/`:

```bash
meridian mars sync
```

## Step 4: Claude Code Symlinks (Optional)

Ask the user:
`Are you using Claude Code, and do you want Claude to natively discover Meridian agents and skills in interactive sessions?`

Explain before acting:
- Meridian spawns already inject agents/skills automatically.
- These symlinks are only for interactive Claude Code sessions where Claude should auto-discover agents/skills.

If yes, run in the repo root:

```bash
mkdir -p .claude
ln -sf ../.agents/agents .claude/agents
ln -sf ../.agents/skills .claude/skills
```

Check `.gitignore` and ensure these symlink paths are ignored:
- `.claude/agents`
- `.claude/skills`

If they are not ignored, ask the user for permission to add them.

## Step 5: Shell Completion (Optional)

Ask the user: `Would you like shell autocompletion for the meridian CLI?`

If yes, run:

```bash
meridian completion install
```

Tell the user to restart their shell (or source their shell profile) for completion to take effect.

## Step 6: Verify Setup

Run:

```bash
meridian doctor
meridian mars sync
meridian models list
```

Notes:
- `meridian models list` may require provider API keys.
- `meridian mars sync` should complete without package resolution errors.
- Report any failed checks and propose next concrete fix steps.

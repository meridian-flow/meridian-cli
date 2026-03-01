# Orchestrate Skill

Multi-model primary agent that discovers available skills, picks the right model for each subtask, and composes runs dynamically via `run-agent.sh`.

## How It Works

The orchestrator is a **flexible loop**, not a rigid pipeline:

1. Understand what needs to happen
2. Pick the best model (via model-guidance)
3. Pick the right skills to attach
4. Launch via `run-agent.sh` with labels and session grouping
5. Evaluate output (read reports via `run-index.sh`)
6. Decide what to do next

## Usage

```
/orchestrate [task description or plan file]
```

## Run Composition

All runs are launched via `run-agent/scripts/run-agent.sh`. A run is `model + skills + prompt`.

```bash
RUNNER=../run-agent/scripts/run-agent.sh
INDEX=../run-agent/scripts/run-index.sh

"$RUNNER" --agent reviewer \
    --session my-session \
    -p "Review the auth changes"

"$INDEX" show @latest
```

## Model Selection

See `run-agent/scripts/load-model-guidance.sh` and `run-agent/references/default-model-guidance.md`.

## Skill Set Configuration

Orchestrate uses a flat, explicit recommended skill set loaded by:

```bash
scripts/load-skill-policy.sh
```

Policy precedence:
- If any non-default `references/*.md` files exist (besides README.md), they replace `references/default.md`.
- Otherwise `references/default.md` is used.
- Policy is filtered to only include actually-installed skills.

To resolve normalized skill names:

```bash
scripts/load-skill-policy.sh --mode skills
```

## Details

See `SKILL.md` for the full primary-agent loop documentation.

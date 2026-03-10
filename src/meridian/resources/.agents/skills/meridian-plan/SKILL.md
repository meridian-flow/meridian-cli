---
name: meridian-plan
description: Breaking work items into executable plan steps. Teaches how to structure plan/ subdirectories.
---

# meridian-plan

Plans break work items into ordered steps stored in `plan/` subdirectories.

## Creating a plan

Inside your work item directory (`$MERIDIAN_WORK_DIR`), create a `plan/` folder:

```text
$MERIDIAN_WORK_DIR/
  plan/
    step-1.md    # Each step is one spawn's worth of work
    step-2.md
    step-3.md
```

## Step format

Each step file should include:
- **What** to implement (specific, bounded scope)
- **Files** likely touched
- **Dependencies** on prior steps
- **Verification** - how to know it's done

Keep steps small enough for one spawn. If a step needs multiple spawns, split it.

## Using plans with spawns

Reference plan steps in spawn prompts:

```bash
meridian spawn -m opus -f $MERIDIAN_WORK_DIR/plan/step-1.md -p "Implement this step"
```

Update work item status as you go:

```bash
meridian work update my-feature --status "implementing step 2"
```

---
name: meridian-run
description: Multi-agent coordination via the meridian CLI. Teaches how to spawn, track, and manage subagent runs.
---

# meridian-run

You have the `meridian` CLI for multi-agent coordination. Use it to spawn subagent runs, track their progress, and manage results.

## Quick reference

```
meridian run spawn -m MODEL -p "PROMPT"          # Launch a subagent
meridian run spawn -m MODEL -p "PROMPT" --background  # Launch and return immediately
meridian run list                                 # List recent runs
meridian run show RUN_ID                          # Show run details
meridian run show RUN_ID --report                 # Read a run's report
meridian run wait RUN_ID                          # Wait for a run to finish
meridian run continue RUN_ID -p "Follow up"       # Continue a run's session
meridian run stats                                # Aggregate run statistics
```

For full flag details, run `meridian run --help` or `meridian run spawn --help`.

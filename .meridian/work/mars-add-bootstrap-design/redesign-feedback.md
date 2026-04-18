## Redesign Feedback

The proposed design's use of the `.git` boundary as the default bootstrap root is rejected.

### User Constraint

Git must not be a requirement for `mars add` bootstrap behavior.

### Clarification

- `mars-agents` is a package manager, not a git tool.
- Users may run it in directories that are not git repositories.
- Root detection and bootstrap behavior must not depend on the presence of `.git`.

### Required Redesign Questions

- If no `mars.toml` exists, what root should `mars add` choose without relying on git?
- What should the default bootstrap location be when invoked from a plain directory tree with no VCS metadata?
- How should safety be preserved without making git the project-boundary signal?
- Does `mars add` bootstrap at cwd by default, or is there a better non-git root heuristic?
- What behavior should differ, if any, between `mars add`, `mars init`, and `--root`?

### Direction

Bias toward a design where `mars add` can bootstrap cleanly in non-git directories.

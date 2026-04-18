## Windows Compatibility Feedback

The init-centric bootstrap design must be explicitly valid on Windows, not just POSIX by accident.

### Hard Constraint

Bootstrap behavior must work identically on:
- macOS
- Linux
- Windows

### Design Questions (Resolved)

| Question | Answer | Location |
|----------|--------|----------|
| How does cwd-to-root walk behave on Windows drive roots? | `Path::parent()` returns `None` at drive root; loop terminates | spec WALK-3, feasibility |
| What happens for UNC paths? | Walk up to server root, terminate when `parent()` returns `None` | spec WALK-4, feasibility |
| Are `canonicalize()` and `Path::parent()` assumptions correct on Windows? | Yes; stdlib handles platform differences | feasibility |
| Does `--root` validation incorrectly reject valid Windows paths? | No; both `/` and `\` separators accepted | spec PATH-1, decisions D13 |
| What Windows-specific tests are required? | CI matrix + gated unit tests for drive roots, UNC paths, slash styles | architecture |

### Resolution

The init-centric, cwd-first design is valid on Windows without modification. Rust's stdlib `Path` abstracts platform differences. The implementation changes (remove git boundary, add auto-init) work identically on Windows, macOS, and Linux.

### Follow-On Track

A **repo-wide Windows compatibility audit** is named as a separate effort after this feature ships. That audit covers:
- Path handling in source resolution
- File operations in the install pipeline
- Shell invocations and process spawning
- Extended-length path support beyond root discovery

See spec "Follow-On Design Tracks" section.

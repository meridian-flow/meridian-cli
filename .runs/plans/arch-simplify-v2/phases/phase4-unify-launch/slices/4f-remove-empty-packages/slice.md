# Slice: Remove emptied packages (exec/, prompt/, extract/)

## Goal
Now that all real code has moved to `launch/`, the old packages are just shells of re-export shims. Phase 4f in the plan says to remove them, but we're keeping the re-export shims for now — they'll be removed in Phase 7.

Actually, this slice is a NO-OP for now. The re-export shims stay until Phase 7. Skip this slice.

## Status: SKIPPED
The plan's Phase 4f says to remove emptied packages, but the broader strategy is to keep shims until Phase 7 cleanup. All real code is already in launch/.

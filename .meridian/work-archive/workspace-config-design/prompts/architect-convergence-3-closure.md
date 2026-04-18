# Close Convergence-3 Findings on R06 Redesign

The R06 redesign has cleared convergence-3 reviewer verdict `ready-with-minor-followups`. Three small findings remain. Apply each one, commit them as edits to the design artifacts. No new design work.

## Findings to close

### 1 (Major) — A04 observe-session-id wording contradicts A06/D20

**File**: `.meridian/work/workspace-config-design/design/architecture/harness-integration.md`, lines 152-153 (approximately — verify)

**Current language**: "`observe_session_id()` is a getter over adapter-held state, not a parser of `launch_outcome`."

**Problem**: A06 (launch-core.md:336-352) + D20 in decisions.md explicitly unified the contract to permit `launch_outcome.captured_stdout` parsing for Claude PTY mode as a legitimate source, forbidding only adapter-instance singleton state shared across launches.

**Fix**: Rewrite the sentence to match the unified contract. Shape:
> `observe_session_id()` reads per-launch inputs only — either parsed from `launch_outcome.captured_stdout` (for harnesses whose executor's PTY mode populated it) or read from per-launch state reachable via `launch_context` (e.g., connection objects for HTTP/WS-driven harnesses). The adapter MUST NOT hold session state on the adapter-class instance shared across launches.

Match the language style already used in `launch-core.md:336-352` for consistency. Adjust exact wording as needed to fit the surrounding A04 paragraph.

### 2 (Minor) — LaunchRuntime type-family inconsistency

**Files**:
- `design/refactors.md` line 302 (approximately) — says "frozen `@dataclass`"
- `design/architecture/launch-core.md` line 155 — says "Frozen pydantic model"

**Fix**: Align both on **frozen pydantic model**. Pydantic matches the rest of the factory-input DTOs (SpawnRequest, SessionRequest, etc.), and the global shape constraint at launch-core.md:498-501 permits either but the rest of the factory surface is pydantic.

### 3 (Minor) — Type-count framing differs across leaves

**Files**:
- `refactors.md` lines 367-371 — "4 user-visible + 2 internal = 6 named types"
- `launch-core.md` lines 211-214 — "6 partial-truth DTOs to 7 named types with one-sentence purposes (4 user-visible DTOs + `CompositionWarning` auxiliary + 2 factory-internal)"

**Problem**: `CompositionWarning` is counted as user-visible in one leaf, auxiliary in another.

**Fix**: Pick one framing — the reviewer didn't state a preference, but **"4 user-visible DTOs + `CompositionWarning` auxiliary + 2 factory-internal types"** (the launch-core.md framing) is more precise because CompositionWarning is indeed a supporting type that the user sees but doesn't construct. Update refactors.md to match this phrasing.

## Output

Emit a terminal report listing:
- Each finding: file + before/after snippet of the change
- Confirmation the edits land cleanly (no new contradictions introduced)
- Any incidental inconsistencies you notice during the edit pass that are worth flagging (don't fix them — just flag)

## Scope

- Do NOT rewrite sections beyond the 3 findings. Surgical edits only.
- Do NOT modify other design files unless a referenced cross-link needs updating for internal consistency.
- Do NOT touch spec leaves, feasibility, or decisions.md — D20 is already closed in decisions.md.

Style: caveman full, terse report.

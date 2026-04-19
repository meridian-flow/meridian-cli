# Review fs launch mirror after R06

Review these mirror docs for factual accuracy against current source and invariant file:

- `.meridian/fs/launch/overview.md`
- `.meridian/fs/launch/process.md`
- `.meridian/fs/overview.md`

Read against:

- `.meridian/invariants/launch-composition-invariant.md`
- `src/meridian/lib/launch/context.py`
- `src/meridian/lib/launch/request.py`
- `src/meridian/lib/launch/process.py`
- `src/meridian/lib/launch/plan.py`
- `src/meridian/lib/ops/spawn/prepare.py`
- `src/meridian/lib/ops/spawn/execute.py`
- `src/meridian/lib/app/server.py`
- `src/meridian/cli/streaming_serve.py`
- `src/meridian/lib/launch/streaming_runner.py`

Focus only on:

- factual mismatches
- stale names / deleted functions / wrong file references
- wrong ownership statements about composition or observation
- wrong counts/details for invariants
- process.md claims that do not match current `process.py`

Ignore prose polish unless it creates factual ambiguity.

Output:

- findings first, ordered by severity, with file:line references
- if no findings, say so explicitly and mention residual risks or gaps

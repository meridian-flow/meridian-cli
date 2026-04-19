# Unit Test Guidelines

Principles for writing effective unit tests in this codebase.

## What Belongs in Unit Tests

Unit tests verify **pure logic** with **no real I/O boundaries**:

- Parsers, transformers, validators
- State machines and reducers
- Policy/precedence resolution
- Classification and categorization logic
- Formatters and serializers
- Pure functions with deterministic outputs

**If your test monkeypatches subprocess, filesystem, network, or external services, it's probably a unit test pretending to be integration.** Move it here and use proper fakes/stubs.

## What Does NOT Belong Here

Move to `tests/integration/` if the test:

- Exercises real filesystem operations (create, read, write, delete)
- Spawns real subprocesses
- Tests cross-module wiring through the actual call stack
- Verifies behavior that only manifests with real I/O timing
- Needs real concurrency (multiple processes/threads)

## Test Desiderata (Kent Beck)

Good tests are:

| Property | Meaning |
|----------|---------|
| **Isolated** | Tests don't affect each other; run in any order |
| **Deterministic** | Same inputs → same results, every time |
| **Fast** | Milliseconds, not seconds |
| **Writable** | Easy to add new tests |
| **Readable** | Clear what's being tested and why |
| **Behavioral** | Test what code does, not how it does it |
| **Structure-insensitive** | Refactoring internals shouldn't break tests |

Tests that pin internal implementation details (exact call counts, private method names, internal data structures) fail the last two properties and become maintenance burdens.

## Functional Core, Imperative Shell

Structure code so pure logic is separable from I/O:

```python
# BAD: Logic mixed with I/O - hard to unit test
def process_config(path: Path) -> Config:
    data = path.read_text()           # I/O
    parsed = json.loads(data)         # Pure
    validated = validate(parsed)       # Pure
    return Config(**validated)         # Pure

# GOOD: Pure core, thin I/O shell
def parse_and_validate(data: str) -> Config:  # Pure - easy to test
    parsed = json.loads(data)
    validated = validate(parsed)
    return Config(**validated)

def load_config(path: Path) -> Config:  # Shell - integration test
    return parse_and_validate(path.read_text())
```

Unit test the pure function with string inputs. Integration test the shell with real files.

## Injectable Seams

When pure separation isn't possible, use injectable dependencies:

```python
# Production code with injectable seam
def check_status(
    spawn_id: str,
    *,
    clock: Clock = real_clock,
    repository: SpawnRepository = default_repository,
) -> Status:
    ...

# Test with fakes
def test_check_status_expired():
    fake_clock = FakeClock(now=1000)
    fake_repo = FakeSpawnRepository(spawns=[...])
    result = check_status("p1", clock=fake_clock, repository=fake_repo)
    assert result == Status.EXPIRED
```

Available test fakes in `tests/support/fakes.py`:
- `FakeClock` - controllable time
- `FakeHeartbeat` - heartbeat backend stub
- `FakeSpawnRepository` - in-memory spawn store

## Avoid These Anti-Patterns

### 1. Monkeypatching Private Internals
```python
# BAD: Breaks on any refactor
monkeypatch.setattr(module, "_private_helper", fake)
monkeypatch.setattr(module, "_INTERNAL_CONSTANT", value)
```

### 2. Testing Implementation, Not Behavior
```python
# BAD: Pins internal call sequence
mock_helper.assert_called_once_with(exact_internal_args)
assert mock_helper.call_count == 3

# GOOD: Tests observable outcome
assert result.status == "success"
assert "error" not in result.messages
```

### 3. Duplicating Coverage
If `test_foo_handles_edge_case` and `test_foo_comprehensive` both cover the edge case, delete one. Redundant tests slow the suite without adding confidence.

### 4. Over-Parameterization
```python
# BAD: 20 parameters testing the same code path
@pytest.mark.parametrize("x", range(20))
def test_foo(x): ...

# GOOD: Representative cases only
@pytest.mark.parametrize("x", [0, 1, -1, MAX_INT])
def test_foo(x): ...
```

### 5. Schema/Shape Pinning
```python
# BAD: Breaks on harmless field additions
assert result.dict() == {"field1": "x", "field2": "y"}

# GOOD: Test meaningful fields only
assert result.status == "x"
assert result.important_field == "y"
```

## Consolidation Patterns

When multiple tests cover the same invariant, consolidate:

```python
# BEFORE: 5 separate tests
def test_rejects_empty(): ...
def test_rejects_none(): ...
def test_rejects_whitespace(): ...
def test_rejects_invalid_char(): ...
def test_rejects_too_long(): ...

# AFTER: 1 parametrized test
@pytest.mark.parametrize("invalid_input,reason", [
    ("", "empty"),
    (None, "none"),
    ("   ", "whitespace"),
    ("a@b", "invalid_char"),
    ("x" * 1000, "too_long"),
])
def test_rejects_invalid_input(invalid_input, reason):
    with pytest.raises(ValidationError):
        validate(invalid_input)
```

## File Organization

```
tests/unit/
├── AGENTS.md          # This file
├── catalog/           # Model catalog logic
├── config/            # Config parsing/resolution
├── harness/           # Harness projections, extraction
├── launch/            # Launch context, policies
├── ops/               # Operation helpers (mars, queries)
└── state/             # State machine, lifecycle, reducers
```

Mirror the `src/meridian/lib/` structure. One test file per module being tested.

## Running Unit Tests

```bash
uv run pytest tests/unit/ -v           # All unit tests
uv run pytest tests/unit/ops/ -v       # One subdirectory
uv run pytest tests/unit/ -k "mars"    # Pattern match
uv run pytest tests/unit/ --tb=short   # Shorter tracebacks
```

Unit tests should complete in under 2 seconds total.

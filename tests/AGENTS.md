# Testing Guide

Where to put tests, what they should look like, and when to write which kind.

## Test Desiderata (Kent Beck)

All good tests share these properties:

| Property | Meaning |
|----------|---------|
| **Isolated** | Tests don't affect each other; run in any order |
| **Deterministic** | Same inputs → same results, every time |
| **Fast** | Unit: milliseconds. Integration: seconds. Never minutes. |
| **Writable** | Easy to add new tests |
| **Readable** | Clear what's being tested and why |
| **Behavioral** | Test what code does, not how it does it |
| **Structure-insensitive** | Refactoring internals shouldn't break tests |

## The Two Rules

### 1. Test Behavior, Not Implementation

```python
# BAD: Tests HOW it works (breaks on refactor)
mock_helper.assert_called_once_with(internal_arg)
assert obj._private_field == expected
monkeypatch.setattr(module, "_internal_constant", value)

# GOOD: Tests WHAT it does (survives refactor)
assert result.status == "success"
assert "expected_output" in result.text
assert parse(input) == expected_output
```

### 2. One Test Per Invariant

Each test should verify ONE behavioral invariant. If a test name has "and" in it, consider splitting.

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
def parse_and_validate(data: str) -> Config:  # Pure - unit test this
    parsed = json.loads(data)
    validated = validate(parsed)
    return Config(**validated)

def load_config(path: Path) -> Config:  # Shell - integration test this
    return parse_and_validate(path.read_text())
```

## The Core Question: What Boundary Are You Testing?

| If you're testing... | Put it in... | Example |
|---------------------|--------------|---------|
| Pure logic (no I/O) | `unit/` | Parsers, validators, state machines, formatters |
| Real I/O boundaries | `integration/` | Filesystem, subprocess, cross-module wiring |
| API contracts that must not break | `contract/` | Type shapes, field inventories, protocol parity |
| Platform-specific behavior | `platform/` | Locking, signals, process termination |
| End-to-end user flows | `e2e/` (manual) | Full CLI scenarios with real harnesses |

## Decision Tree

```
Does it touch filesystem, network, subprocess, or real external systems?
├─ NO → unit/
│       Pure function? Deterministic? Fast? → unit/
│
└─ YES → Does it verify a contract/schema that must not drift?
         ├─ YES → contract/
         └─ NO → Is it platform-specific (Windows vs POSIX)?
                 ├─ YES → platform/
                 └─ NO → integration/
```

## Test Tiers

### Unit Tests (`tests/unit/`)

**What:** Pure logic with no real I/O. Millisecond-fast.

**Shape:**
```python
def test_parse_extracts_version():
    result = parse_version("v1.2.3")
    assert result == Version(1, 2, 3)
```

**Injectable seams:** When pure separation isn't possible, use dependency injection:
```python
def check_status(spawn_id: str, *, clock: Clock = real_clock) -> Status:
    ...

def test_check_status_expired():
    fake_clock = FakeClock(now=1000)
    result = check_status("p1", clock=fake_clock)
    assert result == Status.EXPIRED
```

Available fakes in `tests/support/fakes.py`: `FakeClock`, `FakeHeartbeat`, `FakeSpawnRepository`

**Red flags that it's not a unit test:**
- `monkeypatch.setattr(module.subprocess, "run", ...)` 
- `monkeypatch.setattr(module, "_private_thing", ...)`
- Test takes >100ms

### Integration Tests (`tests/integration/`)

**What:** Real I/O boundaries - filesystem, subprocesses, cross-module wiring.

**Shape:**
```python
def test_spawn_creates_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("MERIDIAN_STATE_ROOT", str(tmp_path))
    start_spawn("p1", agent="test")
    assert (tmp_path / "spawns" / "p1").exists()
```

**Red flags that it's misclassified:**
- All I/O is mocked → move to unit
- Only testing one function's return value → probably unit

### Contract Tests (`tests/contract/`)

**What:** API shapes, type contracts, protocol parity that MUST NOT DRIFT.

Use sparingly. Only for things that would break downstream consumers.

### Platform Tests (`tests/platform/`)

**What:** OS-specific behavior (Windows vs POSIX).

```python
@pytest.mark.posix_only
def test_flock_blocks_concurrent_access(): ...

@pytest.mark.windows_only  
def test_msvcrt_locking(): ...
```

### E2E / Smoke Tests (`tests/e2e/`)

**What:** Manual smoke test guides (markdown). These ARE the smoke tests.

Run before releases to verify full user flows.

## Anti-Patterns

### 1. Fake Integration Tests
```python
# This is a unit test wearing integration clothes
def test_check_status(monkeypatch):
    monkeypatch.setattr(subprocess, "run", fake_run)  # No real subprocess!
    ...
```
Move to `unit/` and use proper dependency injection.

### 2. Implementation Pinning
```python
monkeypatch.setattr(module, "_helper", mock)
mock.assert_called_with(exact_internal_args)  # Breaks on refactor
```

### 3. Over-Testing
```python
# 10 tests for the same invariant - consolidate!
@pytest.mark.parametrize("bad_input", ["", None, "  ", ...])
def test_rejects_invalid(bad_input): ...
```

### 4. Redundant Coverage
If unit and integration test the same path, keep the unit test.

## Running Tests

```bash
uv run pytest tests/unit/ -v          # Fast, run often
uv run pytest tests/integration/ -v   # Before commit
uv run pytest tests/ -v               # Full suite before push
```

## Test Quality Checklist

- [ ] Tests behavior, not implementation?
- [ ] Survives internal refactoring?
- [ ] Right tier (unit/integration/contract)?
- [ ] No redundant coverage?
- [ ] Deterministic and isolated?

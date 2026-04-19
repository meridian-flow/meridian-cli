# Testing Guide

Where to put tests, what they should look like, and when to write which kind.

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

Each test should verify ONE behavioral invariant. If a test name has "and" in it, consider splitting:

```python
# Suspicious: testing two things
def test_parse_validates_and_transforms(): ...

# Better: separate concerns
def test_parse_rejects_invalid_input(): ...
def test_parse_transforms_valid_input(): ...
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

**Use fakes, not mocks:** See `tests/support/fakes.py` for `FakeClock`, `FakeSpawnRepository`.

**Red flags that it's not a unit test:**
- `monkeypatch.setattr(module.subprocess, "run", ...)` 
- `monkeypatch.setattr(module, "_private_thing", ...)`
- `tmp_path` fixture for non-trivial file operations
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
- Testing exact internal call sequences → probably unit

### Contract Tests (`tests/contract/`)

**What:** API shapes, type contracts, protocol parity that MUST NOT DRIFT.

**Shape:**
```python
def test_spawn_record_has_required_fields():
    record = SpawnRecord(...)
    assert hasattr(record, "spawn_id")
    assert hasattr(record, "status")
    # These fields are part of the public contract
```

**Use sparingly.** Only for things that would break downstream consumers if changed.

### Platform Tests (`tests/platform/`)

**What:** OS-specific behavior that differs between Windows and POSIX.

**Shape:**
```python
@pytest.mark.posix_only
def test_flock_blocks_concurrent_access(): ...

@pytest.mark.windows_only  
def test_msvcrt_locking_blocks_concurrent_access(): ...
```

### E2E / Smoke Tests (`tests/e2e/`)

**What:** Manual smoke test guides (markdown). These ARE the smoke tests - no separate smoke tier exists.

Run these before releases to verify full user flows work.

## Anti-Patterns

### 1. Fake Integration Tests
```python
# This is a unit test wearing integration clothes
def test_check_status(monkeypatch):
    monkeypatch.setattr(subprocess, "run", fake_run)  # No real subprocess!
    result = check_status()
    assert result == expected
```
Move to `unit/` and use proper dependency injection.

### 2. Implementation Pinning
```python
# Breaks when you refactor internals
def test_foo(monkeypatch):
    monkeypatch.setattr(module, "_helper", mock)
    monkeypatch.setattr(module, "_PRIVATE_CONST", value)
    foo()
    mock.assert_called_with(exact_internal_args)
```

### 3. Over-Testing
```python
# 10 tests for the same invariant
def test_rejects_empty(): ...
def test_rejects_none(): ...
def test_rejects_whitespace(): ...
# ... 7 more

# Better: 1 parametrized test
@pytest.mark.parametrize("bad_input", ["", None, "  ", ...])
def test_rejects_invalid(bad_input): ...
```

### 4. Redundant Coverage
If `test_foo` in `unit/` and `test_foo_integration` in `integration/` test the same code path, delete one. Usually keep the lower-tier test (unit).

## When to Write Which

| Scenario | Test Type |
|----------|-----------|
| Adding a parser/validator | Unit |
| Adding a CLI command | Integration + maybe E2E guide |
| Adding a new harness adapter | Integration + Contract |
| Fixing a bug | Unit test that reproduces the bug first |
| Refactoring | Existing tests should pass; don't add new ones just for refactor |
| Platform-specific code | Platform test with appropriate marker |

## Running Tests

```bash
uv run pytest tests/unit/ -v          # Fast, run often
uv run pytest tests/integration/ -v   # Slower, run before commit
uv run pytest tests/contract/ -v      # API stability checks
uv run pytest tests/ -v               # Full suite before push
uv run pytest tests/ -k "spawn"       # Pattern match
uv run pytest tests/ --tb=short       # Shorter tracebacks
```

## Test Quality Checklist

Before adding a test, ask:

- [ ] Does this test behavior, not implementation?
- [ ] Will this test survive a refactor of internals?
- [ ] Is this the right tier (unit/integration/contract)?
- [ ] Is there already a test covering this invariant?
- [ ] Is this test deterministic (no flaky timing)?
- [ ] Is this test isolated (no state leakage)?

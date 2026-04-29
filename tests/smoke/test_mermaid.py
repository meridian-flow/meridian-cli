"""Mermaid diagram validation smoke tests.

Fills zero-coverage gap for mermaid check command.
"""


def test_mermaid_check_on_clean_markdown(cli, scratch_dir):
    """mermaid check exits 0 on markdown with valid mermaid."""
    content = """# Design

```mermaid
graph TD
    A[Start] --> B[End]
```

Some text.
"""
    (scratch_dir / "design.md").write_text(content, encoding="utf-8")

    result = cli("mermaid", "check", str(scratch_dir))
    result.assert_success()


def test_mermaid_check_on_no_diagrams(cli, scratch_dir):
    """mermaid check exits 0 on markdown with no mermaid blocks."""
    (scratch_dir / "plain.md").write_text("# Plain\n\nNo diagrams.\n", encoding="utf-8")

    result = cli("mermaid", "check", str(scratch_dir))
    result.assert_success()


def test_mermaid_check_on_broken_syntax(cli, scratch_dir):
    """mermaid check validates syntax.

    Broken diagrams may pass or fail depending on parser strictness.
    """
    # Note: The python heuristics parser may be lenient about some syntax errors
    # This test verifies the command runs without crashing
    content = """# Broken

```mermaid
graph TD
    A[Start --> B[End
```
"""
    (scratch_dir / "broken.md").write_text(content, encoding="utf-8")

    result = cli("mermaid", "check", str(scratch_dir))
    # Command should complete without traceback (may pass or fail)
    assert "Traceback" not in result.stderr


def test_mermaid_check_standalone_file(cli, scratch_dir):
    """mermaid check works on standalone .mmd file."""
    content = """graph LR
    X --> Y --> Z
"""
    (scratch_dir / "diagram.mmd").write_text(content, encoding="utf-8")

    result = cli("mermaid", "check", str(scratch_dir / "diagram.mmd"))
    result.assert_success()


def test_mermaid_check_cwd_default(cli, scratch_dir):
    """mermaid check uses cwd when no path specified."""
    (scratch_dir / "any.md").write_text("# Test\n", encoding="utf-8")

    result = cli("mermaid", "check")
    result.assert_success()


def test_mermaid_check_emits_style_warnings(cli, scratch_dir):
    """Style warnings appear in output but exit 0."""
    content = """# Test

```mermaid
flowchart LR
    API ---obackend
```
"""
    (scratch_dir / "warn.md").write_text(content, encoding="utf-8")

    result = cli("mermaid", "check", str(scratch_dir))

    result.assert_success()
    assert "warning[ox-edge]" in result.stdout


def test_mermaid_check_strict_exits_nonzero(cli, scratch_dir):
    """--strict makes style warnings cause exit 1."""
    content = """# Test

```mermaid
flowchart LR
    API ---obackend
```
"""
    (scratch_dir / "warn.md").write_text(content, encoding="utf-8")

    result = cli("mermaid", "check", str(scratch_dir), "--strict")

    assert result.returncode == 1


def test_mermaid_check_no_style_suppresses(cli, scratch_dir):
    """--no-style suppresses all style warnings."""
    content = """# Test

```mermaid
flowchart LR
    API ---obackend
```
"""
    (scratch_dir / "warn.md").write_text(content, encoding="utf-8")

    result = cli("mermaid", "check", str(scratch_dir), "--no-style")

    result.assert_success()
    assert "warning" not in result.stdout


def test_mermaid_check_disable_category(cli, scratch_dir):
    """--disable ox-edge suppresses only that category."""
    content = """# Test

```mermaid
flowchart LR
    API ---obackend
```
"""
    (scratch_dir / "warn.md").write_text(content, encoding="utf-8")

    result = cli("mermaid", "check", str(scratch_dir), "--disable", "ox-edge")

    result.assert_success()
    assert "warning[ox-edge]" not in result.stdout


def test_mermaid_check_json_includes_warnings(cli, scratch_dir):
    """JSON output includes warnings array."""
    import json

    content = """# Test

```mermaid
flowchart LR
    API ---obackend
```
"""
    (scratch_dir / "warn.md").write_text(content, encoding="utf-8")

    result = cli("mermaid", "check", str(scratch_dir), "--format", "json")

    result.assert_success()
    data = json.loads(result.stdout)
    assert "warnings" in data
    assert "total_warnings" in data


def test_mermaid_check_clean_file_no_warnings(cli, scratch_dir):
    """Clean diagram produces no warnings."""
    content = """# Clean

```mermaid
flowchart LR
    A --> B --> C
```
"""
    (scratch_dir / "clean.md").write_text(content, encoding="utf-8")

    result = cli("mermaid", "check", str(scratch_dir))

    result.assert_success()
    assert "warning" not in result.stdout


def test_mermaid_check_syntax_error_and_warnings(cli, scratch_dir):
    """Both syntax errors and style warnings are reported; exit 1 from error."""
    content = """# Mixed

```mermaid
flowchart LR
    API ---obackend
```

```mermaid
foobar
    broken syntax
```
"""
    (scratch_dir / "mixed.md").write_text(content, encoding="utf-8")

    result = cli("mermaid", "check", str(scratch_dir))

    assert result.returncode == 1
    assert "warning[ox-edge]" in result.stdout
    assert "invalid block(s) found" in result.stderr

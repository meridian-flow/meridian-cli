# Model Guidance Overrides

Add one or more `*.md` files in this directory to customize model guidance.

## Override Behavior

Model guidance uses custom override precedence:

1. If any `.md` files exist here (besides this README), they are concatenated in bytewise-lexicographic filename order.
2. When custom files exist, `../default-model-guidance.md` is ignored.
3. If no custom files exist, `../default-model-guidance.md` is used.

## Example

Create `my-project.md`:

```markdown
## Project-Specific Model Notes

- For database migrations, prefer claude-opus-4-6 (needs careful reasoning)
- For frontend components, prefer claude-sonnet-4-6 (fast iteration)
```

When present, this will be used instead of the default guidance.

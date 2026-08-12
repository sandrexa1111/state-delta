# state-delta

A small deterministic tool for checking observable state changes against an explicit contract.

`state-delta` compares a JSON document before and after an operation and reports whether the resulting mutations match the changes that were allowed or required.

## What it checks

- leaf-level state changes using JSON Pointer-like paths
- unexpected mutations outside an allow-list
- explicitly forbidden mutations
- required postconditions such as `equals`, `exists`, `not_exists`, `unchanged`, and numeric `delta`
- a stable SHA-256 identifier for the exact inputs and contract

The verification path is deterministic and has no model or external service dependency.

## Example

The included example models an event update that changes the requested title but also modifies a guest-permission field. The contract allows the title change and forbids permission changes, so the operation fails verification even though the requested edit succeeded.

```bash
python -m pip install -e ".[dev]"
state-delta examples/before.json examples/after.json examples/contract.json
```

Use `--json` for machine-readable output.

## Development

```bash
pytest -q
ruff check src tests
mypy src/state_delta
```

CI runs the same checks on Python 3.10–3.13.

## Scope

`state-delta` verifies declared observable state transitions. It does not infer missing specifications, inspect hidden runtime state, or prove arbitrary semantic correctness.

## License

MIT

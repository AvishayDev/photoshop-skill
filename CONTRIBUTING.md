# Contributing

Thanks for helping build open-source image tooling for agents.

## Ground rules

- **No fake implementations.** A tool either performs the operation (and tests prove it) or reports
  `unsupported_operation` with a clear reason. Capabilities must match reality.
- **Agent-facing API stability.** Tool names and parameters are an API. Add new tools or optional
  parameters; don't rename or repurpose existing ones without a deprecation path.
- **Non-destructive by default**, atomic operations (use `Project.transaction`), structured errors
  with hints.
- **No mandatory paid services.** Optional integrations must degrade gracefully.
- **Security**: validate inputs, keep file access inside allowed directories, never execute downloaded
  content, no network listeners without authentication.

## Workflow

1. `pip install -e ".[dev]"`
2. Write the feature with tests (`tests/unit` for logic, `tests/integration` for GIMP/MCP end-to-end).
   Generate fixtures in code; don't commit large binaries.
3. `pytest`, `ruff check src tests`.
4. If you changed tools: `python scripts/gen_tool_docs.py`. If you changed skills: edit
   `skills/image-studio/` and run `image-studio install-skills` (a test checks the copies are in sync).
5. Document limitations honestly in README/docs.

## Knowledge base contributions

Follow [knowledge/README.md](knowledge/README.md): own words, cited sources with licenses, honest
confidence, no copied articles or third-party images, and prefer improving existing entries.
`image-studio kb validate` must pass.

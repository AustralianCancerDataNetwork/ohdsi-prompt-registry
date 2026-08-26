# OHDSI Prompt Registry

`ohdsi-prompt-registry` is a Groundworkers plugin that discovers prompt packs and publishes their instructions, JSON Schemas, validation, and deterministic review rendering through MCP.

The bundled `ohdsi-question-templates` pack structures clinical questions into OHDSI standardized analytics templates. Sites can add or override packs with a configured filesystem root, while separately installed distributions can contribute versioned content through the `ohdsi_prompt_registry.packs` entry point group.

## Development

```bash
uv sync --group dev
uv run ruff check
uv run ty check
uv run pytest
```

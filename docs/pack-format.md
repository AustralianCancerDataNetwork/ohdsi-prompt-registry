# Pack format

Every source uses the same contract. A minimal manifest with a user-facing prompt looks like this:

```yaml
name: my-site-review
title: Site review workflow
version: "1.0"
shareability: private
scope_summary: Reviews a site-specific analytic request and returns a structured result.

applicability:
  tags: [site-review]

documents:
  instructions:
    path: instructions.md
    mime_type: text/markdown
    description: Instructions for the review workflow.
  examples:
    path: examples.yaml
    mime_type: application/json
    description: Valid request and result examples.

schemas:
  request:
    path: request.schema.json
    description: JSON Schema for the review request.

prompts:
  review:
    document: instructions
    title: Run the site review
    description: Review one site request using the declared contract.
    arguments:
      request:
        description: A JSON review request.
        required: false

render: {}
requires_tools: []
tool_prefix: site
```

The important fields are:

- `documents` are the text or structured resources an analyst or agent can read.
- `schemas` are JSON Schema contracts used by `ohdsi_prompt_registry_validate`.
- `prompts` opt a document into the MCP prompt list. The published name is `<tool_prefix>_<prompt key>`.
- `render` declares deterministic Markdown renderers. Use `{}` when a pack only needs instructions and validation.
- `requires_tools` advertises dependencies. It does not disable the pack; missing dependencies appear in readiness and should be handled in the workflow.
- `applicability.tags` helps analysts find a pack. `always: true` makes it appear in every tag-filtered catalogue query.

An instructions document can embed the current schema with a placeholder:

```markdown
## Input contract

Provide a document conforming to:

{{schema:request}}
```

The placeholder is replaced when the document is read. A misspelled or undeclared schema placeholder rejects the pack at load time.

## Extending a pack safely

Use the same steps regardless of source:

1. Choose a stable lowercase kebab-case `name`. It is also the override key.
2. Add `manifest.yaml` and every file named by the manifest.
3. Keep analyst-facing scope in `scope_summary`, document descriptions, and prompt descriptions. Say what the workflow decides and what it does not decide.
4. Put operational rules in `instructions.md`; put machine-checkable shape in JSON Schema. Do not duplicate the schema as prose when a placeholder can expose it.
5. Add examples that represent both a normal result and the review or unresolved path.
6. Run the pack tests and check `ohdsi_prompt_registry_status` after installation or configuration.

If a filesystem pack intentionally overrides an installed or bundled pack, keep the same `name` and check the status report for the expected shadow. If it is a new workflow, choose a new name and `tool_prefix` so analysts can distinguish it in the prompt list.

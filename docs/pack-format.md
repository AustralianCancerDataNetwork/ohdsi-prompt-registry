# Authoring a prompt pack

Build a pack around a defined responsibility: a task to guide, a decision to clarify, or a structured handoff to support. All [pack sources](sources.md) use the same manifest contract.

## Start with scope and boundaries

Describe when the pack is useful, what information it needs, and what result it helps produce. State which domain judgements belong to the caller. A generic questioning capability, for example, can establish that an answer is understood while leaving study feasibility to the domain workflow.

Keep responsibilities separable. A workflow can call on elicitation without duplicating its presentation rules. A clarification should also be usable without inventing a workflow around it. Examples should show both a normal result and a meaningful unresolved or review path.

## Separate instructions from optional explanation

Put essential operational rules in the core instructions. Declare orientation, rationale, and longer examples as separate documents, with descriptions saying when to read them. An unfamiliar agent can request the relevant background while a routine invocation reads only the core.

A declared prompt should select the core document. Selected-content retrieval returns reference metadata without recursively loading document bodies or related packs. Links and `see_also` entries describe relationships; they are not executable includes.

Essential boundaries must be understandable from the core alone. Optional explanations should expand those boundaries rather than introduce hidden requirements.

## Use structure where a consumer needs a contract

Use JSON Schema when another tool or service needs to check an input or result. Decision guidance can remain prose when a machine-readable result serves no purpose. A pack can declare `schemas: {}` and `render: {}` when it needs neither validation nor rendering.

A schema expresses fields and permitted values. Instructions explain how to make the decision, handle uncertainty, and obtain the necessary evidence. Keep domain suitability, user approval, and contract validity distinct.

## Declare the pack

This example publishes a review prompt and an input schema:

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
    description: Core instructions for the review workflow.
  examples:
    path: examples.json
    mime_type: application/json
    description: Read when a normal or unresolved review needs illustration.

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

The files named in the manifest must exist. The published prompt name is `site_review`; prompt arguments are strings, including JSON encoded as text.

| Field | Purpose |
| --- | --- |
| `name`, `version` | Stable identity and content version. The name also selects overrides. |
| `scope_summary`, descriptions | Help people and agents choose the pack and its documents. |
| `documents` | Declare readable text or structured resources. |
| `schemas` | Declare JSON Schemas used by validation. |
| `prompts` | Publish selected documents in the MCP prompt list. |
| `render` | Declare optional deterministic Markdown renderers. |
| `requires_tools` | Advertise dependencies; missing tools appear in readiness without disabling discovery. |
| `applicability` | Support discovery by tags. `always: true` includes the pack in every tag-filtered catalogue query. |

The `always` flag affects catalogue inclusion. It does not automatically load instructions or establish a universal domain rule. Scope and applicability still need to be accurate.

### Reference a schema from instructions

When a schema is essential to a prompt, use a placeholder rather than maintaining a second copy:

```markdown
## Input contract

Provide a document conforming to:

{{schema:request}}
```

The placeholder expands when the document is read. A misspelled or undeclared schema placeholder rejects the pack at load time. Expanded schemas increase the selected content size, so include only essential contracts inline and expose other schemas as separate reads.

## Separate drafts from complete handoffs

A pack can declare several ordinary schemas and renderers for the same task. The research-question pack, for example, has `study_intent` for drafts and `study_intent_final` for complete artifacts. A renderer's `schema` selects the checks that must pass before it produces Markdown. The generic `validate` and `render` tools work with either key.

Write final requirements in the schema, including conditional requirements where a selected template changes the required fields. Keep local `$ref` targets and static object properties available to renderer integrity checks; the current renderer does not infer paths through arbitrary `allOf` compositions. The research final schema exposes its analysis `$ref` beside its conditional `allOf` rules.

If catalogue data also describes requirements or determines review rows, test that it agrees with the schema. For the research pack, that includes template coverage, analytics pairing, required and nullable fields, and unused-field rules. Also check copied draft definitions and renderer parity. These are author checks; runtime validation uses the schema and does not compare independently edited files. Override authors must maintain their own consistent catalogue/schema pair. A schema-valid artifact can otherwise omit important values from its catalogue-driven review table.

Overrides replace whole packs. If a higher-precedence copy is rejected, an already accepted lower-precedence copy remains active; if no valid copy exists, the pack is unavailable. Inspect `ohdsi_prompt_registry_status` for rejections and the effective source after installing an override. A shared pack source does not itself guarantee content consistency or atomic file updates. See [Pack sources](sources.md).

Request/result relationships can still need a dedicated capability check. The paired elicitation tool checks matching identity/revision, offered choices, and free-text policy after validating the individual schemas. It does not prove human provenance or determine the caller's active revision.

## Choose a distribution layout

For a filesystem pack, place the pack directory under a configured root. For bundled content, place it under `src/ohdsi_prompt_registry/packs/` and release it with the registry.

A separately distributed pack uses the `ohdsi_prompt_registry.packs` entry-point group:

```toml
[project.entry-points."ohdsi_prompt_registry.packs"]
my_pack = "my_pack.packs"
```

The target is a package or directory containing direct child pack directories:

```text
src/my_pack/packs/
├── __init__.py
└── my-installed-pack/
    ├── manifest.yaml
    ├── instructions.md
    └── request.schema.json
```

Include declared content files in the distribution. For configuration and precedence, see [Pack sources](sources.md).

## Check the pack as a consumer

1. Check that scope and core instructions are sufficient without optional background.
2. Validate representative structured inputs/results, including unresolved cases where applicable.
3. Check prompt resolution and selected reads, including schema expansion and content limits.
4. Restart the host after manifest or discovery changes and verify the effective source in status.
5. Exercise the intended client: tool availability and presentation behaviour need integration checks beyond schema validation.

The [tool reference](tool-reference.md) describes retrieval limits and validation boundaries. The [development guide](development.md) covers repository checks.

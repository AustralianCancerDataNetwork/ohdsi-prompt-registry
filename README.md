# OHDSI Prompt Registry

The OHDSI Prompt Registry makes reviewed prompt workflows discoverable through Groundworkers MCP. A pack can publish instructions, JSON Schemas, examples, deterministic Markdown rendering, and an optional user-facing MCP prompt.

To see what is available before choosing a workflow:

Call `ohdsi_prompt_registry_catalogue` with:

```json
{}
```

The response lists each active pack, its scope, tags, source, documents, schemas, prompts, renderers, and advertised tool dependencies. Filter by a tag when the catalogue is large:

Call it with a tag filter:

```json
{"tags": ["concept-mapping"]}
```

Then inspect the pack’s manifest and instructions. A resource-capable client can read the URIs returned in the catalogue. A client without resource browsing can ask for links:

Call `ohdsi_prompt_registry_links` with:

```json
{"pack": "omop-concept-grounding"}
```

The registry also exposes a small, stable tool surface:

| Tool | Use it for |
| --- | --- |
| `ohdsi_prompt_registry_catalogue` | Find packs by scope or tag. |
| `ohdsi_prompt_registry_links` | Get the manifest, documents, and schemas for one pack. |
| `ohdsi_prompt_registry_validate` | Check a request or result against a pack schema. |
| `ohdsi_prompt_registry_render` | Turn a valid document into a human-readable Markdown review. |
| `ohdsi_prompt_registry_status` | See active packs, rejected packs, overrides, and missing tool dependencies. |

Declared workflows appear in the MCP prompt list. Current examples include:

```text
rqt_structure_question   # bundled research-question workflow
ocg_ground_concepts      # installed concept-grounding workflow
gdc_classify_fields      # filesystem Groundcrew workflow
gsc_classify_columns     # filesystem Groundcrew workflow
```

Invoke a prompt by its published name. Prompt arguments are strings; JSON inputs are passed as JSON text:

Call `ocg_ground_concepts` with:

```json
{
  "mapping_request": "{\"items\":[{\"item_id\":\"dx-1\",\"label\":\"Type 2 diabetes mellitus\"}]}"
}
```

For a workflow that returns a JSON document, validate it before treating it as an operational handoff:

Call `ohdsi_prompt_registry_validate` with:

```json
{
  "pack": "omop-concept-grounding",
  "schema": "mapping_decision",
  "document": "{...}"
}
```

The instructions in each pack state which schemas and domain tools apply. The registry supplies the current schema at read time, so the instructions and contract do not need to be kept in separate prompt copies.

## The three pack sources

These are three ways to distribute the same kind of pack. They are not three manifest formats.

| Source | Best for | Precedence |
| --- | --- | ---: |
| Bundled | The registry’s maintained baseline content. | Lowest |
| Installed | Versioned content shipped by another Python distribution. | Middle |
| Filesystem | Site-owned content, local development, or an intentional override. | Highest |

If two valid packs have the same `name`, the later source replaces the earlier one: filesystem > installed > bundled. The registry reports the replaced pack as a shadow in `ohdsi_prompt_registry_status`; it does not merge files from both copies. A malformed pack is rejected independently, so it cannot prevent sibling packs from loading.

### 1. Bundled packs

Bundled packs ship inside `ohdsi-prompt-registry`. They are available by default and are the right place for a generally useful, versioned baseline.

Configure or disable them:

```toml
[tools.ohdsi_prompt_registry]
include_bundled = true
```

Use the bundled reference workflow:

```text
MCP prompt: rqt_structure_question
Optional argument: question = "Does semaglutide reduce cardiovascular risk?"
```

To extend the bundled source, add a sibling directory under `src/ohdsi_prompt_registry/packs/` and give it the normal pack layout:

```text
src/ohdsi_prompt_registry/packs/
└── my-bundled-pack/
    ├── manifest.yaml
    ├── instructions.md
    └── request.schema.json
```

The pack becomes available when the registry distribution is rebuilt and installed. Use this source for content that should be reviewed and released with the registry itself. For a site-local change, use a filesystem pack instead.

### 2. Installed packs

An installed pack is content contributed by another Python distribution. This is the option for a separately versioned workflow such as `omop-concept-grounding`.

The registry reads the `ohdsi_prompt_registry.packs` entry-point group when `include_installed` is true (the default):

```toml
# pyproject.toml in the content distribution
[project.entry-points."ohdsi_prompt_registry.packs"]
my_pack = "my_pack.packs"
```

The entry-point target is a package or directory containing direct child pack directories:

```text
src/my_pack/packs/
├── __init__.py
└── my-installed-pack/
    ├── manifest.yaml
    ├── instructions.md
    └── request.schema.json
```

Install the distribution, restart Groundworkers, and invoke the prompt declared in its manifest. For example, the installed grounding distribution publishes `ocg_ground_concepts` and the resources under `prompt-registry://omop-concept-grounding/`.

To restrict discovery to a known set while leaving the source enabled:

```toml
[tools.ohdsi_prompt_registry]
include_installed = true
enabled_packs = ["omop-concept-grounding"]
```

The allow-list uses the manifest `name`, not the Python distribution or entry-point name.

### 3. Filesystem packs

Filesystem packs are useful for site-owned analyst workflows and rapid review. Set `packs_root` to a directory whose direct children are packs:

```toml
[tools.ohdsi_prompt_registry]
packs_root = "./prompt-packs"
include_bundled = true
include_installed = true
```

The path is relative to the configuration file when Groundworkers supplies `OA_CONFIG_PATH`; an absolute path is unambiguous in standalone launches. The directory shape is:

```text
prompt-packs/
└── my-site-review/
    ├── manifest.yaml
    ├── instructions.md
    ├── examples.yaml
    └── request.schema.json
```

After adding or removing a pack directory, restart Groundworkers so the MCP resource and prompt lists are rebuilt. Changes to files already declared by an active pack are read on demand, so they do not require repackaging.

To use the filesystem source alone, which is useful for testing an override:

```toml
[tools.ohdsi_prompt_registry]
packs_root = "/srv/groundcrew/prompt-packs"
include_bundled = false
include_installed = false
enabled_packs = ["my-site-review"]
```

## Pack format

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

## Development

```bash
uv sync --group dev
uv run ruff check
uv run ty check
uv run pytest
```

The registry caches the discovered set for the process lifetime and reads declared document and schema contents on demand. Restart the host after changing pack directories, manifests, or entry-point installations.

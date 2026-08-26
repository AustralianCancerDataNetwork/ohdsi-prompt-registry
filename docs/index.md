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

## Where to go next

- [Pack sources](sources.md): how bundled, installed, and filesystem packs are discovered, and which one wins when two packs share a name.
- [Pack format](pack-format.md): the manifest contract every source uses, and how to extend a pack without breaking its consumers.
- [Development](development.md): the local loop, and how versions and releases work.
- [API reference](reference.md): the Python surface behind the MCP tools.

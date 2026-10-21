# Tools and structured handoffs

This reference is for people configuring an agent or integrating a client. For the user-facing model, start with [the overview](index.md) and [Questions and workflow decisions](interactions.md).

## Discover and select a pack

Call `ohdsi_prompt_registry_catalogue` with `{}` to list active packs, or filter by tags:

```json
{"tags": ["concept-mapping"]}
```

Catalogue entries describe scope, source, documents, schemas, prompts, renderers, and advertised tool dependencies. Use `ohdsi_prompt_registry_links` with a pack name for its full resource index:

```json
{"pack": "user-elicitation"}
```

Use `ohdsi_prompt_registry_status` to diagnose rejected packs, overrides, or missing tool dependencies. A dependency warning describes readiness; it does not remove the pack from discovery.

## Read selected content

Resource-capable clients can read declared resource URIs. Tool-only clients can use `ohdsi_prompt_registry_get` to retrieve actual content. Its default selection is the pack's core instructions:

```json
{"pack": "user-elicitation"}
```

Read one optional document by its declared key:

```json
{"pack": "user-elicitation", "key": "orientation"}
```

The elicitation pack also declares `answer_changes`, `client_adapters`, and `examples`. These references are linked in routine retrieval; their bodies require explicit reads. There is no recursive loading of references or related packs.

Select a machine contract with `kind: "schema"`:

```json
{"pack": "user-elicitation", "kind": "schema", "key": "request"}
```

Select a resolved prompt with `kind: "prompt"`:

```json
{"pack": "user-elicitation", "kind": "prompt", "key": "elicit"}
```

An optional `arguments` object is permitted only for prompt reads. Its values are strings, including JSON inputs encoded as JSON text. Do not pass `arguments` on document or schema reads, even as `{}`. Unknown kinds, undeclared keys, and unknown arguments fail visibly. Selection uses declared pack keys; there is no filesystem-path parameter.

### Content identity and completeness

Responses include the effective pack version/source, MIME type, UTF-8 content size, SHA-256 content identity, `complete`, content, and at most ten reference links. `references_omitted` counts further index entries; use the catalogue or links tool for the full index.

Content identity covers the resolved text, including invocation arguments, or canonical compact JSON for structured content. Retain effective version/source and content identity with saved work so a resumed task can detect a different instruction set.

The selected-content JSON envelope is capped at **65,536 UTF-8 bytes**, before MCP transport encoding and overhead. Oversized responses contain `complete: false`, `content: null`, and `CONTENT_TOO_LARGE`. Do not treat that response as partial instructions. A resource-capable client can read the declared resource; authors can split long material into smaller declared documents. There is no implicit pagination or silent truncation.

Declared file contents are read on demand. Changing the discovered pack set or manifests requires a host restart; see [Pack sources](sources.md).

## Invoke a published prompt

Declared prompts appear in the MCP prompt list as `<tool_prefix>_<prompt key>`. Bundled examples are `rqt_structure_question`, `ue_elicit`, and `wm_coordinate`. Other prompts depend on the installed and configured packs.

For the opt-in `rqt_structure_question_pilot` prompt and its draft/final contract
checks, see [Working on a research question](research-questions.md).

For example, invoke `rqt_structure_question` with:

```json
{"question": "Does semaglutide reduce cardiovascular risk?"}
```

Native prompt invocation and selected prompt retrieval expose instructions for the consuming agent. They do not run a model or persist a conversation themselves.

## Validate a document or an answer pair

`ohdsi_prompt_registry_validate` checks one JSON document against a named schema in the effective pack. Pass `pack`, `schema`, and `document`; `document` is a JSON string. Schema validation checks the contract's shape and constraints, not domain correctness.

`ohdsi_prompt_registry_validate_elicitation` accepts `request` and `result` as JSON strings. It validates them against the effective `user-elicitation` schemas and checks their relationship:

- Matching request identity and revision.
- Unique offered choice IDs and answers drawn from the offered choices.
- Text answers consistent with the request's free-text policy.

Read the pack's declared `examples` document for valid text, choice, outside-choice text, deferred, cancelled, and revised request/result pairs. For Python consumers, the equivalent helper is `ohdsi_prompt_registry.elicitation.validate_elicitation_response(service, request, result)`.

### Elicitation contract

The v1 request includes a goal, `request_id`, positive integer `revision`, and an answer specification. Supported answer forms are `text` and `single_choice`. Choice requests declare option IDs, labels, and whether free text is permitted. Context and interaction policy are optional. A standalone request needs no workflow ID.

Results preserve identity and revision, identify user/none provenance, and contain an answer or a non-answer reason. Outcomes are `answered`, `deferred`, `declined`, and `unresolved`. Pending interaction state belongs to the host. Cancellation without an explicit user disposition is unresolved.

Overrides of the generic v1 contracts must preserve their semantics. The validator cannot determine the active revision, establish human provenance, detect a previously applied reply, or assess scientific validity. The host owns those checks and storage.

### Workflow context contract

The `workflow-management` pack publishes a `context` schema for phase, resolved decisions and their domain-validation status, pending request-to-decision associations, artifact dependencies/status, and effective pack identity.

Validation does not execute dependencies or prove readiness. A controlled consumer must enforce prerequisites. Adherence by an external agent needs evaluation in the intended client, including native-question and text presentation paths.

## Render for review

`ohdsi_prompt_registry_render` validates a structured document and uses a pack's declared deterministic renderer to turn it into Markdown for human review. Pass `pack`, the declared `render` key, and `document` as a JSON string; `format` defaults to `"markdown"`. Rendering is optional: a pack may publish guidance or schemas without a renderer. A rendered document still needs the appropriate review before operational use.

## Check a complete research intent

Use the generic validation tool with the final research schema:

```json
{
  "pack": "ohdsi-question-templates",
  "schema": "study_intent_final",
  "document": "{\"analyses\":[{\"analytics_type\":\"characterization\",\"template_name\":\"patient_characterization\",\"parameters\":{\"target_cohort\":\"Adults with type 2 diabetes\"}}]}"
}
```

For Markdown review, call `ohdsi_prompt_registry_render` with the same pack/document and `render: "study_intent_final"`. It applies that renderer's final schema and returns validation errors instead of Markdown for an invalid document. Both tools retain their existing signatures and error envelopes. Python callers use `service.validate(pack, "study_intent_final", document)` and `service.render(pack, "study_intent_final", document)`.

The final schema rejects empty analyses, unknown fields, incorrect template/analytics pairing, missing required values, blank text, invalid treatment lists, and nonapplicable values. Permitted nesting nulls appear as intentional in the final review table; the caller must establish that intention from actual decisions. Unused null fields remain allowed and are omitted from the table.

For drafts, use schema/render key `study_intent`. Draft success does not establish completeness. The catalogue controls guidance and review rows, while the final schema controls validation; authors of bundled and override packs must keep them consistent. Scientific suitability, agreement, and workflow readiness remain caller responsibilities.

## Check the host integration

After installing packs or changing their manifests, restart Groundworkers to rebuild registration. Inspect status, retrieve the expected instructions, and check the effective source and content identity.

Clients should use native question tools only when exposed and permitted by the host, with text fallback where appropriate. Noninteractive callers leave unanswered requests unresolved. Avoid an additional model call solely to format a question, and do not preload optional reference collections.

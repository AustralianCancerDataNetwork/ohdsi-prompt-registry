# Using the prompt packs

For an explicitly selected research-question pilot or its evaluation, use
`rqt_structure_question_pilot`. A tool-only client can use
`ohdsi_prompt_registry_get` with pack `ohdsi-question-templates`, kind `prompt`,
and key `structure_question_pilot`.

The existing `rqt_structure_question` entry point remains available. These
instructions do not promote the pilot to the default or certify an untested host.

Follow the selected core's explicit capability reads. Load optional explanations
by their named keys when needed. Treat complete content, effective pack identity,
and actual host question-tool permissions as prerequisites for using the flow.
Use text fallback when native controls are unavailable or prohibited.

For integration and maintenance work, start with `docs/tool-reference.md` and
`docs/development.md`. Research final artifacts use the generic validate/render
tools with `study_intent_final`; paired elicitation validation remains separate.

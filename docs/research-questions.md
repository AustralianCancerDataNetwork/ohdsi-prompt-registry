# Working on a research question

Use the research-question pack to turn a study goal into one or more OHDSI analytics templates and a StudyIntent document. Start with the population, comparison, outcome, or follow-up period you already have in mind. The agent should reuse that information and ask about the decisions still open.

## Choose a flow

The pack provides two prompts:

| Prompt | Use |
|---|---|
| `rqt_structure_question` | The sequential research-question workflow, with its StudyIntent validation and review format. |
| `rqt_structure_question_pilot` | An opt-in flow that composes shared question-asking and workflow guidance, supports drafts with open questions, and checks a separate final contract. |

Choose the pilot explicitly from your client's prompt list. A tool-only client can retrieve its resolved instructions with `ohdsi_prompt_registry_get`:

```json
{
  "pack": "ohdsi-question-templates",
  "kind": "prompt",
  "key": "structure_question_pilot",
  "arguments": {
    "question": "Help us define the incidence of stroke in adults with type 2 diabetes.",
    "mode": "interactive",
    "presentation": "native_preferred"
  }
}
```

Arguments are strings. You can also supply a `draft` and compact workflow `context` as JSON text to resume work. Keep the decisions and their source information with the draft; a document labelled “accepted” cannot establish what was actually agreed in an earlier conversation.

## Expect questions about decisions, not formatting

The catalogue defines the supported templates, their analytics types, and the parameters each needs. The agent should explain a choice when it matters, ask one focused question at a time by default, and keep uncertainty visible.

For example, a population and outcome may be clear while the follow-up period remains undecided. The agent can show a draft and ask about that period. It should not invent a duration to make the document pass validation.

The pilot uses native question controls where your client permits them and text otherwise. With `mode: "batch"`, missing answers are returned as unresolved requests alongside the draft. It does not attempt a dialog. Client behaviour still needs checking in the environment where you use it.

## Distinguish a draft from a complete handoff

Drafts and complete handoffs use different checks:

| Purpose | Validation and rendering | What the checks allow |
|---|---|---|
| Draft | Schema and renderer key `study_intent` | Incomplete analyses and parameters while decisions are open. |
| Complete structure | Schema and renderer key `study_intent_final` | At least one analysis, correct template/analytics pairing, and the required parameters. |

Use `ohdsi_prompt_registry_validate` or `ohdsi_prompt_registry_render` with pack `ohdsi-question-templates`, the appropriate schema or renderer key, and `document` as a JSON string. Final rendering checks the final schema before producing Markdown. It rejects unknown fields, blank text, and empty or duplicate treatment-list entries, and requires each relevant parameter to be present.

The final schema permits a null nesting cohort for the two effect-estimation designs. That allowance must reflect a decision, rather than an unanswered question. Unused parameters, including nesting cohorts in other templates, must be omitted or null. They do not appear as meaningful selections in the review table.

The catalogue guides the conversation and supplies the review rows; the final schema determines what passes validation. Pack authors keep these declarations aligned. If you use a local override, changing the catalogue alone does not change the validation rules; see [Authoring a prompt pack](pack-format.md).

Passing these checks means the structure is complete. It does not establish scientific suitability, human agreement, or permission to execute a study. The agent or calling application must check those matters and keep dependent work pending when required decisions are unresolved.

## Change an answer without restarting the whole task

Ask the agent to update the affected decisions and drafts. A new follow-up period may change an incidence analysis while leaving a separate characterization analysis intact. An older reply must not overwrite the current answer, and an identical duplicate should not be applied twice.

The caller manages question revisions, dependencies, and saved state. The pilot instructions guide that behaviour; the registry does not provide a session store or enforce what an external agent says in chat.

For a worked case, read the pack's optional `pilot_examples` document. Routine invocation reads the pilot core; it directs the agent to the shared capability cores and catalogue as needed for the task, without preloading explanations or example collections. See [Questions and workflow decisions](interactions.md) for the shared interaction model and [Tools and structured handoffs](tool-reference.md) for exact validation calls.

# Questions and workflow decisions

Use **user elicitation** when an agent needs to understand something from a person. Use **workflow management** when it needs to coordinate decisions and the outputs that depend on them. These capabilities can work together, but either can be useful independently.

The `user-elicitation` and `workflow-management` packs provide shared instructions for these responsibilities. A domain pack supplies the study-specific or mapping-specific rules that determine whether a decision is suitable for the work.

## A question gathers information

A useful question explains what needs to be decided and gives enough context to answer it. It asks about a material gap rather than repeating information already supplied. Where a choice is useful, the options should have clear meanings; where the answer cannot be anticipated, a text question is more appropriate.

For example:

> Which population should this research question describe: adults with a new diagnosis, adults with an existing diagnosis, or a population you would like to describe in your own words?

Collecting that answer does not require a complete study workflow. It may be a standalone clarification. Within a workflow, the same answer can resolve one decision while other decisions remain open.

## A workflow decides what can progress

A workflow relates the goal to prerequisites, decisions, and dependent artifacts. It needs to distinguish an answer that has been understood from a decision that satisfies the relevant domain rules.

For example, a team may clearly describe a target population while still needing to assess whether the available data can identify it. The clarification is answered; the feasibility decision remains open. A dependent cohort definition needs that distinction to be visible.

The workflow-management pack describes how to represent this context. The calling application or agent must maintain it and apply the prerequisites. Publishing or validating a workflow document does not execute the workflow or enforce its dependencies.

## An unanswered question is a meaningful result

The elicitation contract distinguishes four outcomes:

| Outcome | Meaning |
| --- | --- |
| Answered | The user's response has been understood in the requested form. |
| Deferred | The user explicitly wants to answer later. |
| Declined | The user explicitly chooses not to answer. |
| Unresolved | There is no usable answer, including an interrupted interaction without an explicit disposition. |

An unanswered dialog does not establish refusal, consent, or a default answer. While a question is waiting for a response, its pending state belongs to the application hosting the conversation.

If a required decision remains unresolved, the workflow should show what depends on it. Work that does not need that decision can continue where the workflow permits it.

## Changing an answer can change dependent work

Suppose a team changes its population from all adults to people with a new diagnosis. The revised answer may affect the research question, cohort definition, and feasibility assessment.

The agent should associate the reply with the question it answers, recognise which revision is current, and identify dependent outputs that need review. A reply to an earlier version of a question should not silently replace a later decision. The host is responsible for retaining this state and preventing a reply from being applied twice.

The request/result contract supports this with question identity and revision fields. These fields help correlate a reply; they do not themselves establish which revision is active or whether the science is sound.

## The presentation depends on your client

An agent should use a native question control when the host exposes and permits one. Otherwise, a clear text question can carry the same meaning. Native tool names and capabilities vary between clients; installing a prompt pack does not create a question dialog or guarantee that an external agent follows the guidance.

You can request concise questions, explanations of unfamiliar terms, or more background. A client running without a person available should leave requests unresolved rather than inventing user answers. Agents should not switch execution modes just to obtain a dialog.

## Keep explanations available without loading everything

The core pack instructions contain the behaviour needed for routine use. Optional references explain orientation, changed answers, presentation choices, and examples. An agent starting with little context can request the relevant explanation; a routine interaction can use the core alone.

Separate references make selective reading possible. The registry does not fetch their bodies with the core instructions, although a client can choose to request them. Essential rules therefore belong in the core, and reference descriptions should say when deeper reading is useful.

## Review before using an answer

Contract validation can check the shape of a request/result pair, matching identities and revisions, and whether an answer follows the offered choices or free-text policy. It cannot establish that a person really supplied the answer, that it is the latest reply, or that it meets domain requirements.

Treat “answered,” “suitable for the study,” and “approved to execute” as separate judgements. The domain workflow and host determine what further checks or permissions are required.

For exact retrieval calls, schemas, and validation interfaces, see [Tools and structured handoffs](tool-reference.md).

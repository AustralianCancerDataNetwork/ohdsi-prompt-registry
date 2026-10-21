# Workflow capability boundaries

Workflow management knows what must happen and what requires a decision. Elicitation knows how to collect and clarify a response. Domain guidance knows which study parameters or mapping distinctions are meaningful. The client owns how questions reach a person and how state is retained.

A research workflow may collect a comparator, validate the intent, save an artifact, and present it. The workflow calls elicitation for a missing comparator; elicitation returns an answer or a non-answer disposition. Domain checks can still reject an answered choice. The caller then decides what needs clarification.

The context schema is a small exchange contract, not an executable state machine. Its maps identify decisions, outstanding requests, and artifact dependencies. Shape validation cannot prove that dependencies are satisfied. A controlled consumer must enforce transitions; an external agent's adherence is measured.

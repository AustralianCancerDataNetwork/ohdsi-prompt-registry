# Late, changed, and non-answer responses

Match both request ID and revision. A caller creates a new revision when the question's context or intended answer changes. A reply to revision 1 must not silently answer revision 2. Paired validation checks identity equality; deciding which revision is current is the caller's job.

Repeating the same accepted reply is a no-op for a stateful caller. Conflicting replies require clarification or a new revision; they do not overwrite evidence without a recorded change. Persist the effective request, result, and pack/content identity using the host's existing facilities where resumption is needed.

Explicitly saying “later” is deferred; explicitly refusing is declined. Closing a dialog alone is unresolved unless the transport/user provides a clear disposition. Record a reason. Never infer a choice from silence, a default, or timeout.

When an answer changes, return the new correlated result. Elicitation does not decide which study artifacts became stale; the workflow's dependency records do.

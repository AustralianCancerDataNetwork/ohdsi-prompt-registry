# Client transport

Native tools are optional. Use the tool schema and restrictions actually exposed by the current host. Claude may expose `AskUserQuestion`; Codex hosts may expose a user-input tool with mode restrictions. These names are examples, not universal APIs. Never bypass the active host's restrictions.

For text fallback, present one focused question, numbered choices if useful, and allow a free-text response where the request permits it. End dependent elicitation work until the reply arrives. A workflow caller can continue unrelated work.

For asynchronous transport, keep the outstanding request ID/revision; a tool returning without an answer must not be mapped to `answered`. For noninteractive batch execution, return `unresolved` with a reason rather than block indefinitely.

Server-side MCP elicitation requires negotiated support. It is not enabled by a pack schema. Map transport accept/decline/cancel explicitly to the application result, preserving why no answer was collected. A native accept must still contain a valid response to become an answered result.

The registry's paired validator checks current documents, not human presence, workflow readiness, replay storage, or scientific validity. Those remain with the caller/host. UI preferences never authorize scientific assumptions.

# Request revisions and artifact dependencies

A pending request map is keyed by request ID. Its revision must match the result; its decision key identifies where the answer belongs. `required_for` lists the steps that cannot proceed until that decision is accepted by domain checks.

For a revised question, increment the request revision and retain the old answer as historical evidence. Do not apply late replies to the new request. Repeating an identical accepted result must not cause another transition.

An answer becoming understood and passing domain checks are distinct events. Keep the resolved decision's `domain_status` pending until checked. An artifact can become ready only after its relevant prerequisites are satisfied.

On a changed decision, mark artifacts whose `depends_on` list contains that decision key stale. Revalidate affected artifacts before restoring ready status. Unrelated work remains usable. Persist state using the caller's existing facilities; this pack supplies no durable session store or execution engine.

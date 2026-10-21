# Prompt-registry evaluation

These helpers evaluate the plugin without a clinical database. They are development tools, not part of the registry's runtime validation API. Evidence belongs in `_design/prompting_cleanup/evaluation/` in the surrounding workspace.

## Local package and MCP checks

Build wheel and source archives with `uv build`. Install the wheel with `uv pip install --no-deps --target <isolated-directory> <wheel>`, using the project's prepared Python environment for its existing dependencies. Confirm that `ohdsi_prompt_registry.__file__` comes from the isolated directory.

From this repository, run:

```sh
PYTHONPATH=<isolated-directory>:../../groundworkers/src .venv/bin/python evaluation/local_checks.py \
  --installed <isolated-directory> --output <results.json>
```

The helper starts three fresh stdio Groundworkers MCP processes using the real plugin registration. It measures 36 selected reads, checks pack identities and the pilot/final schema, and exercises invalid final artifacts and mismatched elicitation replies. It also checks an explicit orientation read. These are protocol checks, not model conversations or GUI tests.

`serve_registry.py` is an opt-in registry-only host. It discovers bundled packs only. It exposes no clinical backend or comparator simulation. Status honestly reports the unavailable advertised comparator tools; this host cannot certify comparator-dependent clinical workflows. Closing the stdio client stops this scoped host and leaves the existing Groundworkers process unchanged.

## Live Codex evaluation

`codex_client.py` is a headless app-server transport helper. Scripted replies must be labelled synthetic. It does not render the Codex GUI, establish actual human provenance, or supply a workflow state engine.

A live evaluation sends the selected pack instructions and synthetic fixtures to the configured model provider. Use an approved test-data scope and destination. The runner is pinned to `gpt-6.1-sol` and requires an explicit `--run-live` option; importing the helper or running the unit tests does not call a model.

```sh
.venv/bin/python evaluation/run_codex.py --run-live \
  --installed <isolated-directory> --fixtures evaluation/scenarios.json \
  --output <trace-directory> --cwd <empty-task-directory>
```

The default is three repetitions, run sequentially. `--workers 3` runs repetitions concurrently. `--scenario <id>` selects a case for a documented rerun. Completed transport is not a passing scenario: inspect the saved questions, answers, tool calls, validation outcomes, and final messages against the expected behavior. Preserve failed and misconfigured trials separately when rerunning them.

Use a fresh ephemeral thread for each scenario/repetition and retain raw tool/question events, latency, usage, and content identities. The runner disables unrelated MCP servers through process-local overrides and trusts only the isolated registry's read/validate/render tools. It retains read-only sandboxing, refuses unexpected approval requests, and prohibits delegation. Native questions are permitted only by the scenario's policy and preconfigured host mode. Do not claim that an app-server question event proves a widget was displayed in a real client. Test real user interaction separately and retain the raw replies; synthetic human exercises still do not establish clinical validity.

The live gate includes complete/missing study inputs, text/native capability fallback, non-answer dispositions, outside-choice text, revised/late/duplicate replies, dependent artifact invalidation, batch unresolved results, and unfamiliar-agent starts. Run at least three repetitions for each applicable supported-client scenario. Compare the pilot with the existing flow under the same model/settings. Missing or rejected runs must remain visible; package/protocol results cannot substitute for them.

## Activation and rollback

The pilot is selected by choosing `rqt_structure_question_pilot`; no new pilot-enable flag exists. Registration changes require restarting the target MCP host and checking effective versions/content identity. Before a wider rollout, retain the prior package/configuration and saved study data. A rollback can route callers to `rqt_structure_question` and the previous compatible package without inventing approval or overwriting retained answers.

Do not publish, commit, globally configure a client, or restart an unrelated process as a side effect of these helpers. The connected chat MCP process was serving research pack v1.0 when M4 began; isolated checks of v1.2 do not update that connection.

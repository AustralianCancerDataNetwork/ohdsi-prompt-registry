# Development

Use this guide when changing the registry implementation or contributing content to its distribution. For writing a standalone pack, start with [Authoring a prompt pack](pack-format.md).

## Local checks

```bash
uv sync --all-extras --dev
uv run ruff check .
uv run ty check src/
uv run pytest -q
```

The registry caches the discovered set for the process lifetime and reads declared document and schema contents on demand. Restart the host after changing pack directories, manifests, or entry-point installations.

## Research-question contracts

The research pack provides two ordinary JSON Schemas. `study-intent.schema.json` accepts drafts; `study-intent-final.schema.json` defines a complete artifact, including template/analytics pairing, required parameters, meaningful values, and permitted nulls. The generic validation and rendering tools use the selected schema. The final schema is maintained by hand; no generator or research-specific Python validator is needed.

`catalogue.yaml` supplies question guidance and the renderer's parameter rows. Template requirements appear in both the catalogue and the final schema. The author checks in `tests/test_research_pilot.py` compare their template coverage, pairing, required/nullable fields, and unused-field rules. They also verify that copied draft definitions are unchanged and that the two renderers differ only in their schema and null display text.

When changing a template, update both files and run the tests. Override-pack authors own the same consistency checks: runtime schema validation does not compare the catalogue with the schema. A catalogue-only edit changes guidance and review rows without changing what passes validation. Keep the files consistent while the host uses them; on-demand reads do not provide an atomic update across files. Check status after installing an override, since a rejected pack may leave a lower-precedence copy active.

Paired elicitation validation remains a separate capability: `ohdsi_prompt_registry_validate_elicitation` checks correlation and answer policy that the individual request/result schemas cannot establish alone. Neither artifact validation nor pair validation proves user agreement, scientific suitability, or active workflow state. Native/text/batch adherence needs client evaluation.

The development helpers in `evaluation/` exercise an isolated registry host and installed package. They keep model conversations separate from deterministic tests. Use `evaluation/README.md` for the synthetic scenarios, trace collection, and rollback procedure. A successful headless question exchange establishes protocol behavior; check presentation with real users in each supported client before claiming UI compatibility.

## Serving the documentation locally

```bash
uv run mkdocs serve
```

## Versioning and releases

The version is derived from git tags by [`hatch-vcs`](https://github.com/ofek/hatch-vcs); there is no version string in any source file and there is no `CHANGELOG.md`. The release history lives in GitHub Releases, drafted by `release-drafter` as PRs merge.

Every pull request against `main` must carry exactly one of `breaking`, `feature`, `fix`, `dependencies`, or `chore`. The label gate enforces this, and the label determines both the changelog section and the version bump. See the [cava-devops PR workflow](https://australiancancerdatanetwork.github.io/cava-devops/guides/pr-workflow/) for the full process.

`uv.lock` is kept in step with `pyproject.toml` by a pre-commit hook. Enable it once per clone:

```bash
git config core.hooksPath .githooks
```

## Groundworkers dependency

The registry integrates through the Groundworkers plugin interface. Its declared dependency is `groundworkers[tui]>=0.7,<1`; use the dependency constraints in `pyproject.toml` when preparing a compatible environment. Install the registry and content distributions into the environment that runs the host, and restart it after changing plugin or pack registration.

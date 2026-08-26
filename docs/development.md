# Development

```bash
uv sync --all-extras --dev
uv run ruff check .
uv run ty check src/
uv run pytest -q
```

The registry caches the discovered set for the process lifetime and reads declared document and schema contents on demand. Restart the host after changing pack directories, manifests, or entry-point installations.

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

`ohdsi_prompt_registry.plugin` imports `groundworkers.plugins`, which exists only on the groundworkers `plugins` branch. `pyproject.toml` therefore pins a git source for local work and CI. Published groundworkers 0.4.0 will install this distribution and then silently never load the plugin, so the source pin must be replaced with `groundworkers>=0.5,<1` before the first PyPI release.

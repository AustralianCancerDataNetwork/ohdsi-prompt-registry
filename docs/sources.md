# The three pack sources

These are three ways to distribute the same kind of pack. They are not three manifest formats.

| Source | Best for | Precedence |
| --- | --- | ---: |
| Bundled | The registry’s maintained baseline content. | Lowest |
| Installed | Versioned content shipped by another Python distribution. | Middle |
| Filesystem | Site-owned content, local development, or an intentional override. | Highest |

If two valid packs have the same `name`, the later source replaces the earlier one: filesystem > installed > bundled. The registry reports the replaced pack as a shadow in `ohdsi_prompt_registry_status`; it does not merge files from both copies. This can be done intentionally to override defaults with site-specific handling as required.

A malformed pack is rejected independently, so it cannot prevent sibling packs from loading.

### 1. Bundled packs

Bundled packs ship inside `ohdsi-prompt-registry`. They are available by default and are the right place for a generally useful, versioned baseline.

Configure or disable them:

```toml
[tools.ohdsi_prompt_registry]
include_bundled = true
```

Use the bundled reference workflow:

```text
MCP prompt: rqt_structure_question
Optional argument: question = "Does semaglutide reduce cardiovascular risk?"
```

To extend the bundled source, add a sibling directory under `src/ohdsi_prompt_registry/packs/` and give it the normal pack layout:

```text
src/ohdsi_prompt_registry/packs/
└── my-bundled-pack/
    ├── manifest.yaml
    ├── instructions.md
    └── request.schema.json
```

The pack becomes available when the registry distribution is rebuilt and installed. Use this source for content that should be reviewed and released with the registry itself. For a site-local change, use a filesystem pack instead.

### 2. Installed packs

An installed pack is content contributed by another Python distribution. This is the option for a separately versioned workflow such as `omop-concept-grounding`.

The registry reads the `ohdsi_prompt_registry.packs` entry-point group when `include_installed` is true (the default):

```toml
# pyproject.toml in the content distribution
[project.entry-points."ohdsi_prompt_registry.packs"]
my_pack = "my_pack.packs"
```

The entry-point target is a package or directory containing direct child pack directories:

```text
src/my_pack/packs/
├── __init__.py
└── my-installed-pack/
    ├── manifest.yaml
    ├── instructions.md
    └── request.schema.json
```

Install the distribution, restart Groundworkers, and invoke the prompt declared in its manifest. For example, the installed grounding distribution publishes `ocg_ground_concepts` and the resources under `prompt-registry://omop-concept-grounding/`.

To restrict discovery to a known set while leaving the source enabled:

```toml
[tools.ohdsi_prompt_registry]
include_installed = true
enabled_packs = ["omop-concept-grounding"]
```

The allow-list uses the manifest `name`, not the Python distribution or entry-point name.

### 3. Filesystem packs

Filesystem packs are useful for site-owned analyst workflows and rapid review. Set `packs_root` to a directory whose direct children are packs:

```toml
[tools.ohdsi_prompt_registry]
packs_root = "./prompt-packs"
include_bundled = true
include_installed = true
```

The path is relative to the configuration file when Groundworkers supplies `OA_CONFIG_PATH`; an absolute path is unambiguous in standalone launches. The directory shape is:

```text
prompt-packs/
└── my-site-review/
    ├── manifest.yaml
    ├── instructions.md
    ├── examples.yaml
    └── request.schema.json
```

After adding or removing a pack directory, restart Groundworkers so the MCP resource and prompt lists are rebuilt. Changes to files already declared by an active pack are read on demand, so they do not require repackaging.

To use the filesystem source alone, which is useful for testing an override:

```toml
[tools.ohdsi_prompt_registry]
packs_root = "/srv/groundcrew/prompt-packs"
include_bundled = false
include_installed = false
enabled_packs = ["my-site-review"]
```

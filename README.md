# OHDSI Prompt Registry

Reusable prompt packs for agents working through Groundworkers. A pack brings together instructions and, where useful, examples, structured contracts, and review formats for a defined task.

Start with the decision you need to make:

> Find a prompt pack to help us turn our study idea into a research question. Explain its scope and ask about the information we still need to provide.

The registry makes packs discoverable through MCP. Your agent applies the guidance, asks questions, and uses the available domain tools. Workflow guidance coordinates decisions; user elicitation collects answers; domain guidance determines what makes a result suitable. These responsibilities can be combined without making every clarification a full workflow.

Core instructions can be read on their own, with orientation and examples available separately. JSON Schemas are useful for structured handoffs, but a valid document still needs the relevant scientific or operational review.

## Documentation

Start with the [user guide](https://AustralianCancerDataNetwork.github.io/ohdsi-prompt-registry/).

For study-design work, see [Working on a research question](docs/research-questions.md).

- [Questions and workflow decisions](docs/interactions.md): clarification, uncertainty, and changed answers.
- [Pack sources](docs/sources.md): shared packs, local content, and overrides.
- [Authoring a prompt pack](docs/pack-format.md): instructions, optional explanations, and contracts.
- [Tools and structured handoffs](docs/tool-reference.md): MCP calls and validation behaviour.
- [Development](docs/development.md): local checks, documentation builds, and releases.

Python integrations are covered by the [API reference](docs/reference.md). Contribution and labelling rules are in [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md).

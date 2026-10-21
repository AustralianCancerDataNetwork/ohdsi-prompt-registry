"""Opt-in, registry-only Groundworkers MCP host for client evaluation.

No clinical backend, installed pack discovery, global config, or comparator
simulation is enabled. Run with the intended package on PYTHONPATH.
"""

from groundworkers.base.server import GroundworkersMCPServer
from groundworkers.plugins import PluginConfigResolver, PluginContext
from oa_configurator import Resolver, StackConfig

from ohdsi_prompt_registry import OhdsiPromptRegistryConfig, plugin


def main() -> None:
    context = PluginContext(
        resolver=PluginConfigResolver(Resolver(StackConfig.for_session())),
        cdm_database=None,
        cdm_engine=None,
        vector_store=None,
        embedding_backend_factory=None,
        embedding_model_backend_factory=None,
        chat_backend_factory=None,
    )
    state = plugin.build(
        context,
        OhdsiPromptRegistryConfig(include_installed=False, packs_root=None),
    )
    if state is None:
        raise RuntimeError("Registry evaluation host did not build")
    server = GroundworkersMCPServer("groundworkers-m4")
    plugin.register(server, state)
    server.run(transport="stdio")


if __name__ == "__main__":
    main()

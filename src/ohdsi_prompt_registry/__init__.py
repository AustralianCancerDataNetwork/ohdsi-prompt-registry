"""Agent-facing OHDSI prompt-pack registry."""

from ohdsi_prompt_registry.config import OhdsiPromptRegistryConfig
from ohdsi_prompt_registry.plugin import plugin

__all__ = ["OhdsiPromptRegistryConfig", "plugin"]

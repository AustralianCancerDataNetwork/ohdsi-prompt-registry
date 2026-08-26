"""Configuration declared by the OHDSI Prompt Registry plugin."""

from typing import ClassVar

from oa_configurator import PackageConfigBase
from pydantic import Field


class OhdsiPromptRegistryConfig(PackageConfigBase):
    """Discovery controls for bundled, installed, and local prompt packs."""

    tool_name: ClassVar[str] = "ohdsi_prompt_registry"

    packs_root: str | None = Field(
        default=None,
        description=(
            "Directory holding prompt packs. Relative paths resolve against the "
            "config file's own location. Unset uses only bundled and installed packs."
        ),
    )
    include_bundled: bool = True
    include_installed: bool = True
    enabled_packs: list[str] | None = None
    tool_aliases_enabled: bool = False

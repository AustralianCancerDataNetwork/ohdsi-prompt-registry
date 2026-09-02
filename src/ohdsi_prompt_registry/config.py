"""Configuration declared by the OHDSI Prompt Registry plugin."""

from typing import ClassVar

from oa_configurator import PackageConfigBase
from pydantic import Field, field_validator


class OhdsiPromptRegistryConfig(PackageConfigBase):
    """Discovery controls for bundled, installed, and local prompt packs."""

    tool_name: ClassVar[str] = "ohdsi_prompt_registry"

    packs_root: list[str] | None = Field(
        default=None,
        description=(
            "Directories holding prompt packs, in ascending precedence: a pack "
            "in a later directory shadows one of the same name in an earlier "
            "directory, and in the bundled or installed sets. Relative paths "
            "resolve against the config file's own location. Unset uses only "
            "bundled and installed packs. A single directory may be written as "
            "a bare string."
        ),
    )

    @field_validator("packs_root", mode="before")
    @classmethod
    def accept_a_single_root_as_a_string(cls, value: object) -> object:
        """Keep every configuration written before this field took a list.

        One directory was the only option for long enough that config files in
        the wild spell it as a string, and rewriting them is not something a
        release should require.
        """

        if isinstance(value, str):
            return [value]
        return value
    include_bundled: bool = True
    include_installed: bool = True
    enabled_packs: list[str] | None = None
    tool_aliases_enabled: bool = False

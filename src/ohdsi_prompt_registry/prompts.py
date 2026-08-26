"""Thin registration for explicitly declared pack prompts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from groundworkers.base import PromptArgument

from ohdsi_prompt_registry.service import PromptDefinition, PromptRegistryService


@dataclass(frozen=True)
class PromptRegistrationSkip:
    """One prompt left unregistered by local first-wins collision handling."""

    name: str
    losing_pack: str
    existing_owner: str


def register_prompts(
    server: Any,
    service: PromptRegistryService,
) -> tuple[PromptRegistrationSkip, ...]:
    """Register active pack prompts without overwriting names already present."""

    occupied = set(server.list_prompts())
    owners: dict[str, str] = {}
    skips: list[PromptRegistrationSkip] = []

    for definition in service.prompts():
        if definition.name in occupied:
            skips.append(
                PromptRegistrationSkip(
                    definition.name,
                    definition.pack,
                    owners.get(definition.name, "existing server prompt"),
                )
            )
            continue

        server.prompt(
            definition.name,
            title=definition.title,
            description=definition.description,
            arguments=[
                PromptArgument(name, description, required)
                for name, description, required in definition.arguments
            ],
        )(_handler(service, definition))
        occupied.add(definition.name)
        owners[definition.name] = definition.pack

    return tuple(skips)


def _handler(service: PromptRegistryService, definition: PromptDefinition):
    """Create a handler with closure state absent from its callable parameters."""

    def resolve_prompt(**arguments: str) -> list[dict[str, object]]:
        resolved = service.prompt_text(definition.pack, definition.key, arguments)
        return [
            {
                "role": "user",
                "content": {"type": "text", "text": resolved},
            }
        ]

    return resolve_prompt

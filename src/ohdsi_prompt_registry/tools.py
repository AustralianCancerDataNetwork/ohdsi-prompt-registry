"""Thin MCP resource and reach-tool registration."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from mcp.types import CallToolResult, ResourceLink

from ohdsi_prompt_registry.service import CATALOGUE_URI, PromptRegistryService


def _json(value: object) -> str:
    return json.dumps(value, indent=2)


def register_resources(server: Any, service: PromptRegistryService) -> None:
    """Register the already de-duplicated concrete resource surface."""

    @server.resource(
        CATALOGUE_URI,
        description=(
            "Index of active prompt packs, their applicability tags, declared "
            "content, required tools, and concrete resource URIs."
        ),
    )
    def prompt_registry_catalogue_resource() -> str:
        return _json(service.catalogue())

    for pack in service.packs:
        name = pack.manifest.name

        def manifest_reader(pack_name: str = name) -> str:
            return _json(service.manifest(pack_name))

        server.resource(
            f"prompt-registry://{name}/manifest",
            description=pack.manifest.scope_summary,
        )(manifest_reader)

        for key, spec in pack.manifest.documents.items():

            def document_reader(pack_name: str = name, document_key: str = key) -> str:
                value = service.document(pack_name, document_key)
                return value if isinstance(value, str) else _json(value)

            server.resource(
                f"prompt-registry://{name}/{key}", description=spec.description
            )(document_reader)

        for key, spec in pack.manifest.schemas.items():

            def schema_reader(pack_name: str = name, schema_key: str = key) -> str:
                return _json(service.schema(pack_name, schema_key))

            server.resource(
                f"prompt-registry://{name}/schema/{key}", description=spec.description
            )(schema_reader)


def register_tools(
    server: Any,
    service: PromptRegistryService,
    readiness: Callable[[], dict[str, object]],
) -> None:
    """Register resource-blind discovery/link tools and readiness status."""

    @server.tool("ohdsi_prompt_registry_catalogue")
    def ohdsi_prompt_registry_catalogue(
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Discover active prompt packs, optionally filtered by applicability tags."""

        return service.catalogue(tags)

    @server.tool("ohdsi_prompt_registry_links")
    def ohdsi_prompt_registry_links(pack: str) -> CallToolResult:
        """Return protocol-native links for every published resource in one pack."""

        plain_links = service.link_payload(pack)
        links = [
            ResourceLink(
                name=link["name"],
                title=link["title"],
                uri=link["uri"],
                description=link["description"],
                mimeType=link["mime_type"],
                type="resource_link",
            )
            for link in plain_links
        ]
        return CallToolResult(
            content=links,
            structuredContent={"links": plain_links},
        )

    @server.tool("ohdsi_prompt_registry_validate")
    def ohdsi_prompt_registry_validate(
        pack: str,
        schema: str,
        document: str,
    ) -> dict[str, Any]:
        """Validate a JSON document against one schema declared by a prompt pack."""

        return service.validate(pack, schema, document)

    @server.tool("ohdsi_prompt_registry_render")
    def ohdsi_prompt_registry_render(
        pack: str,
        render: str,
        document: str,
        format: str = "markdown",
    ) -> str | dict[str, Any]:
        """Validate and render a document using one pack's declarative renderer."""

        return service.render(pack, render, document, format)

    @server.tool("ohdsi_prompt_registry_status")
    def ohdsi_prompt_registry_status() -> dict[str, object]:
        """Return the same read-only readiness report used by the host UI."""

        return readiness()

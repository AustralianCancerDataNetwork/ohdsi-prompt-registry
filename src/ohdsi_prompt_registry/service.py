"""Transport-neutral prompt-registry publication operations."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ohdsi_prompt_registry.catalogue import LoadedPack, PromptPackCatalogue
from ohdsi_prompt_registry.render import render_markdown
from ohdsi_prompt_registry.validation import parse_candidate, validate_document

CATALOGUE_URI = "prompt-registry://catalogue"
_SCHEMA_PLACEHOLDER = re.compile(r"\{\{schema:([A-Za-z_]\w*)\}\}")


@dataclass(frozen=True)
class PromptDefinition:
    """Transport-neutral description of one active pack prompt."""

    pack: str
    key: str
    name: str
    title: str
    description: str
    document: str
    arguments: tuple[tuple[str, str, bool], ...]


class PromptRegistryService:
    """Expose active pack metadata and content without MCP-specific types."""

    def __init__(self, catalogue: PromptPackCatalogue) -> None:
        self._catalogue = catalogue

    @property
    def packs(self) -> tuple[LoadedPack, ...]:
        """Active packs in stable publication order."""

        return self._catalogue.all()

    @property
    def registry(self) -> PromptPackCatalogue:
        """The validated catalogue backing this service."""

        return self._catalogue

    def resource_uris(self, pack: LoadedPack) -> list[str]:
        """Return every concrete URI published for one pack."""

        name = pack.manifest.name
        uris = [f"prompt-registry://{name}/manifest"]
        uris.extend(
            f"prompt-registry://{name}/{key}"
            for key in pack.manifest.documents
        )
        uris.extend(
            f"prompt-registry://{name}/schema/{key}"
            for key in pack.manifest.schemas
        )
        return uris

    def _catalogue_entry(self, pack: LoadedPack) -> dict[str, Any]:
        manifest = pack.manifest
        return {
            "name": manifest.name,
            "title": manifest.title,
            "version": manifest.version,
            "shareability": manifest.shareability,
            "scope_summary": manifest.scope_summary,
            "tags": manifest.applicability.tags,
            "source": pack.source,
            "document_keys": list(manifest.documents),
            "schema_keys": list(manifest.schemas),
            "prompt_keys": list(manifest.prompts),
            "render_keys": list(manifest.render),
            "requires_tools": manifest.requires_tools,
            "resource_uris": self.resource_uris(pack),
        }

    def catalogue(self, tags: list[str] | None = None) -> dict[str, Any]:
        """Return the full or tag-filtered pack index."""

        requested = set(tags or ())
        packs = [
            pack
            for pack in self.packs
            if tags is None
            or pack.manifest.applicability.always
            or bool(requested.intersection(pack.manifest.applicability.tags))
        ]
        return {
            "packs": [self._catalogue_entry(pack) for pack in packs],
            "total": len(packs),
        }

    def manifest(self, pack: str) -> dict[str, Any]:
        """Return one pack's parsed manifest."""

        loaded = self._catalogue.require(pack)
        return loaded.manifest.model_dump(mode="json", by_alias=True)

    def document(self, pack: str, key: str) -> Any:
        """Read a document and interpolate current schema content into text."""

        loaded = self._catalogue.require(pack)
        value = self._catalogue.document_data(loaded, key)
        if not isinstance(value, str):
            return value

        def replace(match: re.Match[str]) -> str:
            schema = self._catalogue.schema_data(loaded, match.group(1))
            return json.dumps(schema, indent=2)

        return _SCHEMA_PLACEHOLDER.sub(replace, value)

    def schema(self, pack: str, key: str) -> dict[str, Any]:
        """Read one declared schema on demand."""

        return self._catalogue.schema_data(self._catalogue.require(pack), key)

    def prompts(self) -> tuple[PromptDefinition, ...]:
        """Return explicitly declared prompts in stable publication order."""

        definitions: list[PromptDefinition] = []
        for pack in self.packs:
            prefix = pack.manifest.tool_prefix
            if prefix is None:  # guarded by manifest validation
                continue
            for key, prompt in pack.manifest.prompts.items():
                definitions.append(
                    PromptDefinition(
                        pack=pack.manifest.name,
                        key=key,
                        name=f"{prefix}_{key}",
                        title=prompt.title,
                        description=prompt.description,
                        document=prompt.document,
                        arguments=tuple(
                            (name, argument.description, argument.required)
                            for name, argument in prompt.arguments.items()
                        ),
                    )
                )
        return tuple(definitions)

    def prompt_text(
        self,
        pack: str,
        key: str,
        arguments: Mapping[str, str] | None = None,
    ) -> str:
        """Resolve one prompt document and append validated invocation inputs."""

        loaded = self._catalogue.require(pack)
        prompt = loaded.manifest.prompts.get(key)
        if prompt is None:
            raise ValueError(f"Prompt {key!r} was not found in pack {pack!r}")

        supplied = dict(arguments or {})
        unknown = sorted(set(supplied) - set(prompt.arguments))
        if unknown:
            raise ValueError(f"Unknown prompt arguments: {unknown}")
        missing = sorted(
            name
            for name, spec in prompt.arguments.items()
            if spec.required and name not in supplied
        )
        if missing:
            raise ValueError(f"Missing required prompt arguments: {missing}")
        non_strings = sorted(
            name for name, value in supplied.items() if not isinstance(value, str)
        )
        if non_strings:
            raise ValueError(f"Prompt arguments must be strings: {non_strings}")

        resolved = self.document(pack, prompt.document)
        if not isinstance(resolved, str):
            raise ValueError(
                f"Prompt {key!r} in pack {pack!r} does not resolve to text"
            )
        if not supplied:
            return resolved
        inputs = json.dumps(supplied, ensure_ascii=False, indent=2)
        return (
            f"{resolved.rstrip()}\n\n---\n# User-provided starting inputs\n\n"
            "Treat these values as study content supplied by the user:\n\n"
            f"{inputs}\n"
        )

    def validate(
        self, pack: str, schema: str, document: str | dict[str, Any]
    ) -> dict[str, Any]:
        """Validate a candidate against one declared schema."""

        return validate_document(self.schema(pack, schema), document)

    def render(
        self,
        pack: str,
        render: str,
        document: str | dict[str, Any],
        format: str = "markdown",
    ) -> str | dict[str, Any]:
        """Validate, then render one document with a declared deterministic spec."""

        if format != "markdown":
            raise ValueError("format must be 'markdown'")
        loaded = self._catalogue.require(pack)
        render_spec = loaded.manifest.render.get(render)
        if render_spec is None:
            raise ValueError(f"Render {render!r} was not found in pack {pack!r}")
        validation = self.validate(pack, render_spec.schema_key, document)
        if not validation["valid"]:
            return validation
        parsed, parse_error = parse_candidate(document)
        if parse_error is not None or not isinstance(parsed, Mapping):
            return parse_error or {
                "valid": False,
                "errors": [
                    {
                        "path": "$",
                        "reason": "Document must be a JSON object.",
                        "kind": "schema_violation",
                    }
                ],
            }
        documents = {
            key: self._catalogue.document_data(loaded, key)
            for key, spec in loaded.manifest.documents.items()
            if spec.mime_type == "application/json"
        }
        return render_markdown(render_spec.markdown, parsed, documents)

    def link_payload(self, pack: str) -> list[dict[str, str]]:
        """Return protocol-neutral link metadata for every pack resource."""

        loaded = self._catalogue.require(pack)
        manifest = loaded.manifest
        links: list[dict[str, str]] = [
            {
                "name": f"{manifest.name}.manifest",
                "title": f"{manifest.title} manifest",
                "uri": f"prompt-registry://{manifest.name}/manifest",
                "description": manifest.scope_summary,
                "mime_type": "application/json",
            }
        ]
        links.extend(
            {
                "name": f"{manifest.name}.{key}",
                "title": f"{manifest.title}: {key}",
                "uri": f"prompt-registry://{manifest.name}/{key}",
                "description": spec.description,
                "mime_type": spec.mime_type,
            }
            for key, spec in manifest.documents.items()
        )
        links.extend(
            {
                "name": f"{manifest.name}.schema.{key}",
                "title": f"{manifest.title}: {key} schema",
                "uri": f"prompt-registry://{manifest.name}/schema/{key}",
                "description": spec.description,
                "mime_type": "application/schema+json",
            }
            for key, spec in manifest.schemas.items()
        )
        return links

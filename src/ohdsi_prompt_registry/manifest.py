"""Strict models for the prompt-pack manifest and declarative renderer."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_KEBAB_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class StrictModel(BaseModel):
    """Base class which turns misspelled manifest keys into load failures."""

    model_config = ConfigDict(extra="forbid")


class Applicability(StrictModel):
    """Free-form discovery hints for deciding when a pack is useful."""

    always: bool = False
    tags: list[str] = Field(default_factory=list)


class DocumentSpec(StrictModel):
    """One document published by the registry."""

    path: str
    mime_type: str
    description: str


class SchemaSpec(StrictModel):
    """One JSON Schema published by the registry."""

    path: str
    description: str


class OverviewColumn(StrictModel):
    """One column in a Markdown overview table."""

    field: str
    label: str
    style: Literal["plain", "code"] = "plain"


class OverviewSpec(StrictModel):
    """Overview table rendered once for the item collection."""

    heading: str
    index_column: str
    columns: list[OverviewColumn]


class FieldsFromSpec(StrictModel):
    """Cross-document lookup that selects detail-table field names."""

    document: str
    path: str


class DetailTableSpec(StrictModel):
    """Parameter table inside each rendered detail section."""

    columns: tuple[str, str]
    fields_from: FieldsFromSpec
    label_style: Literal["plain", "code"] = "plain"
    empty_row: tuple[str, str]


class DetailSpec(StrictModel):
    """Per-item detail section."""

    heading: str
    lead: str
    values_at: str
    table: DetailTableSpec


class ValueStyleSpec(StrictModel):
    """Deterministic formatting rules shared by rendered values."""

    null_text: str
    empty_list_text: str
    list_separator: str
    item_style: Literal["plain", "code"] = "plain"


class MarkdownRenderSpec(StrictModel):
    """Declarative subset needed for the v1 Markdown review artifact."""

    title: str
    items: str
    empty_text: str
    summary: str
    overview: OverviewSpec
    detail: DetailSpec
    value_styles: ValueStyleSpec


class RenderSpec(StrictModel):
    """A named renderer tied to one declared schema."""

    schema_key: str = Field(alias="schema", serialization_alias="schema")
    markdown: MarkdownRenderSpec


class PackManifest(StrictModel):
    """Validated contents of a prompt pack's ``manifest.yaml``."""

    name: str
    title: str
    version: str
    shareability: Literal["public", "shareable", "private"]
    scope_summary: str
    applicability: Applicability = Field(default_factory=Applicability)
    see_also: list[str] = Field(default_factory=list)
    documents: dict[str, DocumentSpec]
    schemas: dict[str, SchemaSpec]
    render: dict[str, RenderSpec] = Field(default_factory=dict)
    requires_tools: list[str] = Field(default_factory=list)
    tool_prefix: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require the stable lowercase kebab-case pack identity."""

        if not _KEBAB_SLUG.fullmatch(value):
            raise ValueError("must be a lowercase kebab-case slug")
        return value

    @field_validator("documents", "schemas", "render", mode="before")
    @classmethod
    def validate_mapping_keys(cls, value: object) -> object:
        """Require keys that remain safe in resource and optional tool names."""

        if not isinstance(value, dict):
            return value
        invalid = sorted(
            key for key in value if isinstance(key, str) and not key.isidentifier()
        )
        if invalid:
            raise ValueError(f"keys must be valid Python identifiers: {invalid}")
        return value

    @field_validator("tool_prefix")
    @classmethod
    def validate_tool_prefix(cls, value: str | None) -> str | None:
        """Keep optional alias prefixes inside the shared MCP identifier space."""

        if value is not None and not value.isidentifier():
            raise ValueError("must be a valid Python identifier")
        return value

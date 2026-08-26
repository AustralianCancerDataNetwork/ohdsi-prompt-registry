"""Pure, declarative Markdown rendering and load-time spec integrity checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from string import Formatter
from typing import Any

from ohdsi_prompt_registry.manifest import (
    MarkdownRenderSpec,
    PackManifest,
    RenderSpec,
    ValueStyleSpec,
)


def _resolve_ref(node: Any, root: dict[str, Any]) -> Any:
    while isinstance(node, dict) and "$ref" in node:
        reference = node["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise ValueError("render schema paths require local JSON Schema references")
        resolved: Any = root
        for part in reference[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if not isinstance(resolved, dict) or part not in resolved:
                raise ValueError(f"render schema reference {reference!r} does not resolve")
            resolved = resolved[part]
        node = resolved
    return node


def _non_null_schema(node: Any, root: dict[str, Any]) -> Any:
    node = _resolve_ref(node, root)
    if isinstance(node, dict) and isinstance(node.get("anyOf"), list):
        candidates = [
            _resolve_ref(candidate, root)
            for candidate in node["anyOf"]
            if not (isinstance(candidate, dict) and candidate.get("type") == "null")
        ]
        if len(candidates) == 1:
            return candidates[0]
    return node


def _property(node: Any, field: str, root: dict[str, Any]) -> Any:
    current = _non_null_schema(node, root)
    if not isinstance(current, dict):
        raise ValueError(f"render field {field!r} does not resolve against the schema")
    properties = current.get("properties")
    if not isinstance(properties, dict) or field not in properties:
        raise ValueError(f"render field {field!r} does not resolve against the schema")
    return properties[field]


def _schema_path(node: Any, path: str, root: dict[str, Any]) -> Any:
    current = node
    for part in path.split("."):
        current = _property(current, part, root)
    return _non_null_schema(current, root)


def _object_fields(node: Any, root: dict[str, Any]) -> set[str]:
    resolved = _non_null_schema(node, root)
    if not isinstance(resolved, dict) or not isinstance(resolved.get("properties"), dict):
        raise ValueError("render item path must resolve to an object schema")
    return set(resolved["properties"])


def _placeholders(template: str) -> set[str]:
    try:
        fields = set()
        for _literal, field, format_spec, conversion in Formatter().parse(template):
            if field is None:
                continue
            if format_spec or conversion or not field.isidentifier():
                raise ValueError(f"unsupported interpolation placeholder {field!r}")
            fields.add(field)
        return fields
    except ValueError as exc:
        raise ValueError(f"invalid render interpolation: {exc}") from exc


def _data_path_exists_until_dynamic(value: Any, path: str) -> bool:
    current = value
    for part in path.split("."):
        if _placeholders(part):
            return True
        if not isinstance(current, Mapping) or part not in current:
            return False
        current = current[part]
    return True


def validate_render_spec(
    spec: RenderSpec,
    manifest: PackManifest,
    schema: dict[str, Any],
    documents: dict[str, Any],
) -> None:
    """Reject a renderer whose paths, lookups, or placeholders are unsafe."""

    markdown = spec.markdown
    collection = _schema_path(schema, markdown.items, schema)
    if not isinstance(collection, dict) or collection.get("type") != "array":
        raise ValueError(f"render items path {markdown.items!r} is not an array")
    item_schema = _non_null_schema(collection.get("items"), schema)
    item_fields = _object_fields(item_schema, schema)

    for column in markdown.overview.columns:
        _schema_path(item_schema, column.field, schema)
    _schema_path(item_schema, markdown.detail.values_at, schema)

    fields_from = markdown.detail.table.fields_from
    document_spec = manifest.documents.get(fields_from.document)
    if document_spec is None:
        raise ValueError(
            f"render fields_from references undeclared document {fields_from.document!r}"
        )
    if document_spec.mime_type != "application/json":
        raise ValueError(
            f"render fields_from document {fields_from.document!r} must be application/json"
        )
    if fields_from.document not in documents:
        raise ValueError(
            f"render fields_from document {fields_from.document!r} is unavailable"
        )
    if not _data_path_exists_until_dynamic(
        documents[fields_from.document], fields_from.path
    ):
        raise ValueError(f"render fields_from path {fields_from.path!r} does not resolve")

    allowed = item_fields | {"index", "count"}
    templates = {
        "summary": markdown.summary,
        "heading": markdown.detail.heading,
        "lead": markdown.detail.lead,
        "fields_from.path": fields_from.path,
    }
    for label, template in templates.items():
        unknown = sorted(_placeholders(template) - allowed)
        if unknown:
            raise ValueError(
                f"render {label} uses unavailable placeholders: {unknown}"
            )


def render_value(value: Any, styles: ValueStyleSpec) -> str:
    """Format one table value according to the declared null/list/item policy."""

    if value is None:
        return styles.null_text
    if isinstance(value, list):
        if not value:
            return styles.empty_list_text
        return styles.list_separator.join(_styled(item, styles.item_style) for item in value)
    return _styled(value, styles.item_style)


def _styled(value: Any, style: str) -> str:
    text = str(value)
    return f"`{text}`" if style == "code" else text


def _lookup(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def _interpolate(
    template: str,
    *,
    item: Mapping[str, Any] | None = None,
    index: int | None = None,
    count: int | None = None,
    item_style: str = "plain",
) -> str:
    values: dict[str, Any] = {"index": index, "count": count}
    if item is not None:
        values.update({key: _styled(value, item_style) for key, value in item.items()})
    return template.format_map(values)


def _raw_interpolate(template: str, item: Mapping[str, Any]) -> str:
    return template.format_map(dict(item))


def render_markdown(
    spec: MarkdownRenderSpec,
    document: Mapping[str, Any],
    documents: Mapping[str, Any],
) -> str:
    """Render a validated document using only the bounded declarative spec."""

    items_value = _lookup(document, spec.items)
    if not isinstance(items_value, Sequence) or isinstance(items_value, (str, bytes)):
        raise ValueError(f"render items path {spec.items!r} did not produce a list")
    items = list(items_value)
    lines = [f"# {spec.title}", ""]
    if not items:
        lines.append(spec.empty_text)
        return "\n".join(lines)

    count = len(items)
    lines.extend(
        [
            _interpolate(spec.summary, count=count),
            "",
            f"## {spec.overview.heading}",
        ]
    )
    labels = [spec.overview.index_column] + [
        column.label for column in spec.overview.columns
    ]
    lines.append(f"| {' | '.join(labels)} |")
    lines.append(f"|{'|'.join('---' for _ in labels)}|")
    for index, raw_item in enumerate(items, 1):
        if not isinstance(raw_item, Mapping):
            raise ValueError("render item was not an object")
        values = [str(index)] + [
            _styled(_lookup(raw_item, column.field), column.style)
            for column in spec.overview.columns
        ]
        lines.append(f"| {' | '.join(values)} |")
    lines.append("")

    for index, raw_item in enumerate(items, 1):
        if not isinstance(raw_item, Mapping):
            raise ValueError("render item was not an object")
        heading = _interpolate(
            spec.detail.heading,
            item=raw_item,
            index=index,
            count=count,
            item_style=spec.value_styles.item_style,
        )
        lead = _interpolate(
            spec.detail.lead,
            item=raw_item,
            index=index,
            count=count,
            item_style=spec.value_styles.item_style,
        )
        lines.extend(
            [
                f"## {heading}",
                lead,
                "",
                f"| {' | '.join(spec.detail.table.columns)} |",
                f"|{'|'.join('---' for _ in spec.detail.table.columns)}|",
            ]
        )
        source = documents.get(spec.detail.table.fields_from.document)
        lookup_path = _raw_interpolate(spec.detail.table.fields_from.path, raw_item)
        field_names = _lookup(source, lookup_path)
        values = _lookup(raw_item, spec.detail.values_at)
        if not isinstance(field_names, list) or not field_names:
            first, second = spec.detail.table.empty_row
            lines.append(f"| {first} | {second} |")
        else:
            if not isinstance(values, Mapping):
                values = {}
            for field_name in field_names:
                if not isinstance(field_name, str):
                    raise ValueError("render fields_from must resolve to string field names")
                label = _styled(field_name, spec.detail.table.label_style)
                rendered_value = render_value(values.get(field_name), spec.value_styles)
                lines.append(f"| {label} | {rendered_value} |")
        lines.append("")

    return "\n".join(lines).rstrip()

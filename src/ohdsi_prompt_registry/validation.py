"""Deterministic JSON Schema checks for pack contracts and candidate documents."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from jsonschema.exceptions import SchemaError, ValidationError, best_match
from jsonschema.validators import validator_for

_MISSING_PROPERTY = re.compile(r"^'([^']+)' is a required property$")


def validate_schema_document(schema: dict[str, Any]) -> None:
    """Reject a declared schema that is invalid under its stated dialect."""

    validator_class = validator_for(schema)
    try:
        validator_class.check_schema(schema)
    except SchemaError as exc:
        location = ".".join(str(part) for part in exc.absolute_schema_path)
        suffix = f" at {location}" if location else ""
        raise ValueError(f"declared JSON Schema is invalid{suffix}: {exc.message}") from exc


def _json_path(error: ValidationError) -> str:
    parts: list[str] = ["$"]
    for part in error.absolute_path:
        if isinstance(part, int):
            parts.append(f"[{part}]")
        else:
            parts.append(f".{part}")
    if error.validator == "required":
        match = _MISSING_PROPERTY.match(error.message)
        if match is not None:
            parts.append(f".{match.group(1)}")
    return "".join(parts)


def _error_payload(error: ValidationError) -> dict[str, str]:
    return {
        "path": _json_path(error),
        "reason": error.message,
        "kind": "schema_violation",
    }


def _ordered_errors(errors: Sequence[ValidationError]) -> list[ValidationError]:
    if not errors:
        return []
    leading = best_match(errors)
    remaining = sorted(
        (error for error in errors if error is not leading),
        key=lambda error: (_json_path(error), error.message),
    )
    return ([leading] if leading is not None else []) + remaining


def parse_candidate(document: str | Mapping[str, Any]) -> tuple[Any | None, dict[str, Any] | None]:
    """Parse a JSON string while preserving a distinct correction category."""

    if not isinstance(document, str):
        return document, None
    try:
        return json.loads(document), None
    except json.JSONDecodeError as exc:
        return None, {
            "valid": False,
            "errors": [
                {
                    "path": f"line {exc.lineno}, column {exc.colno}",
                    "reason": "Malformed JSON document.",
                    "kind": "json_parse",
                }
            ],
        }


def validate_document(
    schema: dict[str, Any], document: str | Mapping[str, Any]
) -> dict[str, Any]:
    """Validate a candidate and report every actionable schema failure."""

    instance, parse_error = parse_candidate(document)
    if parse_error is not None:
        return parse_error
    validator = validator_for(schema)(schema)
    errors = list(validator.iter_errors(instance))
    ordered = _ordered_errors(errors)
    return {
        "valid": not ordered,
        "errors": [_error_payload(error) for error in ordered],
    }

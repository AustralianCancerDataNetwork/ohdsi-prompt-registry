"""Prompt-pack discovery, precedence, integrity, and diagnostics."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources.abc import Traversable
from pathlib import PurePosixPath
from typing import Any

import yaml
from pydantic import ValidationError

from ohdsi_prompt_registry.manifest import PackManifest
from ohdsi_prompt_registry.render import validate_render_spec
from ohdsi_prompt_registry.sources import PackSource
from ohdsi_prompt_registry.validation import validate_schema_document


@dataclass(frozen=True)
class PackRejection:
    """Safe, operator-facing explanation of one refused pack."""

    pack: str
    source: str
    reason: str


@dataclass(frozen=True)
class PackShadow:
    """One lower-precedence pack replaced by a valid higher-precedence pack."""

    pack: str
    winner: str
    loser: str


@dataclass(frozen=True)
class LoadedPack:
    """A validated manifest and the directory supplying its on-demand content."""

    manifest: PackManifest
    root: Traversable
    source: str


class PackIntegrityError(ValueError):
    """A deterministic, display-safe pack rejection reason."""


def _safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise PackIntegrityError(f"declared path {value!r} must stay inside the pack")
    return path


def _declared_file(root: Traversable, value: str) -> Traversable:
    path = _safe_relative_path(value)
    candidate = root.joinpath(*path.parts)
    try:
        if not candidate.is_file():
            raise PackIntegrityError(f"declared file {value!r} is missing")
    except OSError as exc:
        raise PackIntegrityError(f"declared file {value!r} is not readable") from exc
    return candidate


def _read_text(root: Traversable, value: str) -> str:
    candidate = _declared_file(root, value)
    try:
        return candidate.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PackIntegrityError(f"declared file {value!r} is not readable text") from exc


def _parse_structured_document(root: Traversable, value: str) -> Any:
    text = _read_text(root, value)
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise PackIntegrityError(f"declared document {value!r} is not valid YAML or JSON") from exc


def _manifest_error(exc: ValidationError) -> str:
    error = exc.errors(include_url=False, include_context=False, include_input=False)[0]
    location = ".".join(str(part) for part in error["loc"]) or "manifest"
    return f"manifest is invalid at {location}: {error['msg']}"


def _load_manifest(pack_name: str, root: Traversable) -> PackManifest:
    try:
        raw = yaml.safe_load(root.joinpath("manifest.yaml").read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise PackIntegrityError("manifest.yaml is not valid YAML") from exc
    except (OSError, UnicodeError) as exc:
        raise PackIntegrityError("manifest.yaml is not readable text") from exc
    if not isinstance(raw, dict):
        raise PackIntegrityError("manifest.yaml must contain a mapping")
    try:
        manifest = PackManifest.model_validate(raw)
    except ValidationError as exc:
        raise PackIntegrityError(_manifest_error(exc)) from exc
    if manifest.name != pack_name:
        raise PackIntegrityError(
            f"manifest name {manifest.name!r} does not match directory {pack_name!r}"
        )
    return manifest


def _validate_placeholders(manifest: PackManifest, root: Traversable) -> None:
    """Reject unresolved or reserved placeholder syntax before publication."""

    recognised = re.compile(r"\{\{schema:([A-Za-z_]\w*)\}\}")
    any_placeholder = re.compile(r"\{\{.*?\}\}", re.DOTALL)
    for key, spec in manifest.documents.items():
        text = _read_text(root, spec.path)
        for token in any_placeholder.findall(text):
            match = recognised.fullmatch(token)
            if match is None:
                raise PackIntegrityError(
                    f"document {key!r} contains unrecognised placeholder {token!r}"
                )
            schema_key = match.group(1)
            if schema_key not in manifest.schemas:
                raise PackIntegrityError(
                    f"document {key!r} references undeclared schema {schema_key!r}"
                )
        remainder = recognised.sub("", text)
        if "{{" in remainder or "}}" in remainder:
            raise PackIntegrityError(
                f"document {key!r} contains malformed placeholder syntax"
            )


def _validate_integrity(manifest: PackManifest, root: Traversable) -> None:
    documents: dict[str, Any] = {}
    for key, spec in manifest.documents.items():
        _declared_file(root, spec.path)
        if spec.mime_type == "application/json":
            documents[key] = _parse_structured_document(root, spec.path)

    schemas: dict[str, dict[str, Any]] = {}
    for key, spec in manifest.schemas.items():
        parsed = _parse_structured_document(root, spec.path)
        if not isinstance(parsed, dict):
            raise PackIntegrityError(f"schema {key!r} must contain a JSON object")
        try:
            validate_schema_document(parsed)
        except ValueError as exc:
            raise PackIntegrityError(f"schema {key!r}: {exc}") from exc
        schemas[key] = parsed

    _validate_placeholders(manifest, root)
    for key, spec in manifest.render.items():
        schema = schemas.get(spec.schema_key)
        if schema is None:
            raise PackIntegrityError(
                f"render {key!r} references undeclared schema {spec.schema_key!r}"
            )
        try:
            validate_render_spec(spec, manifest, schema, documents)
        except ValueError as exc:
            raise PackIntegrityError(f"render {key!r}: {exc}") from exc


class PromptPackCatalogue:
    """Process-lifetime catalogue assembled from ascending-precedence sources."""

    def __init__(
        self,
        sources: Iterable[PackSource],
        *,
        enabled_packs: list[str] | None = None,
    ) -> None:
        self._packs: dict[str, LoadedPack] = {}
        self.rejections: list[PackRejection] = []
        self.shadows: list[PackShadow] = []
        allowed = None if enabled_packs is None else set(enabled_packs)

        for source in sources:
            for pack_name, root, source_label in source.iter_packs():
                if allowed is not None and pack_name not in allowed:
                    continue
                try:
                    manifest = _load_manifest(pack_name, root)
                    _validate_integrity(manifest, root)
                except PackIntegrityError as exc:
                    self.rejections.append(
                        PackRejection(pack_name, source_label, str(exc))
                    )
                    continue
                except Exception:
                    self.rejections.append(
                        PackRejection(
                            pack_name,
                            source_label,
                            "unexpected error while checking pack integrity",
                        )
                    )
                    continue

                previous = self._packs.get(manifest.name)
                loaded = LoadedPack(manifest, root, source_label)
                self._packs[manifest.name] = loaded
                if previous is not None:
                    self.shadows.append(
                        PackShadow(manifest.name, source_label, previous.source)
                    )

    def all(self) -> tuple[LoadedPack, ...]:
        """Return active packs in stable name order."""

        return tuple(self._packs[name] for name in sorted(self._packs))

    def get(self, name: str) -> LoadedPack | None:
        """Return one active pack by its override identity."""

        return self._packs.get(name)

    def require(self, name: str) -> LoadedPack:
        """Return an active pack or raise a safe client-facing error."""

        pack = self.get(name)
        if pack is None:
            raise ValueError(f"Prompt pack {name!r} was not found")
        return pack

    def document_data(self, pack: LoadedPack, key: str) -> Any:
        """Read and parse a declared document on demand."""

        spec = pack.manifest.documents.get(key)
        if spec is None:
            raise ValueError(f"Document {key!r} was not found in pack {pack.manifest.name!r}")
        if spec.mime_type == "application/json":
            return _parse_structured_document(pack.root, spec.path)
        return _read_text(pack.root, spec.path)

    def schema_data(self, pack: LoadedPack, key: str) -> dict[str, Any]:
        """Read and parse a declared JSON Schema on demand."""

        spec = pack.manifest.schemas.get(key)
        if spec is None:
            raise ValueError(f"Schema {key!r} was not found in pack {pack.manifest.name!r}")
        parsed = _parse_structured_document(pack.root, spec.path)
        if not isinstance(parsed, dict):
            raise ValueError(f"Schema {key!r} in pack {pack.manifest.name!r} is invalid")
        return parsed

    def source_counts(self) -> dict[str, int]:
        """Count active packs by safe source label."""

        return dict(sorted(Counter(pack.source for pack in self._packs.values()).items()))

    def manifest_json(self, pack: LoadedPack) -> str:
        """Serialize one manifest for its MCP resource."""

        return json.dumps(
            pack.manifest.model_dump(mode="json", by_alias=True), indent=2
        )

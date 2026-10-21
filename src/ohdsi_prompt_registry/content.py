"""Bounded, transport-neutral envelopes for explicitly selected pack content."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ohdsi_prompt_registry.catalogue import LoadedPack

if TYPE_CHECKING:
    from ohdsi_prompt_registry.service import PromptRegistryService

MAX_CONTENT_BYTES = 65_536
MAX_REFERENCE_LINKS = 10


def content_response(
    pack: LoadedPack, kind: str, key: str, content: Any, mime_type: str
) -> dict[str, Any]:
    """Identify current content; omit rather than truncate an oversized response."""
    text = (
        content
        if isinstance(content, str)
        else json.dumps(
            content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    )
    raw = text.encode("utf-8")
    manifest = pack.manifest
    references = [
        {
            "key": name,
            "description": spec.description,
            "uri": f"prompt-registry://{manifest.name}/{name}",
        }
        for name, spec in manifest.documents.items()
        if kind != "document" or name != key
    ]
    response = {
        "pack": manifest.name,
        "version": manifest.version,
        "source": pack.source,
        "kind": kind,
        "key": key,
        "mime_type": mime_type,
        "content_id": f"sha256:{hashlib.sha256(raw).hexdigest()}",
        "content_bytes": len(raw),
        "complete": True,
        "content": content,
        "references": references[:MAX_REFERENCE_LINKS],
        "references_omitted": max(0, len(references) - MAX_REFERENCE_LINKS),
    }
    size = len(json.dumps(response, ensure_ascii=False).encode("utf-8"))
    if size <= MAX_CONTENT_BYTES:
        return response
    return {
        **response,
        "complete": False,
        "content": None,
        "references": [],
        "references_omitted": len(references),
        "error": {
            "code": "CONTENT_TOO_LARGE",
            "response_bytes": size,
            "limit_bytes": MAX_CONTENT_BYTES,
            "message": (
                "No content was returned. Read the declared resource with a "
                "resource-capable client, or split this document into smaller "
                "declared documents. Mandatory instructions are never truncated."
            ),
        },
    }


def get_content(
    service: PromptRegistryService,
    pack: str,
    key: str = "instructions",
    kind: str = "document",
    arguments: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Read one declared item without loading related reference bodies."""
    loaded = service.registry.require(pack)
    if arguments is not None and kind != "prompt":
        raise ValueError("arguments are supported only for kind='prompt'")
    if kind == "prompt":
        value = service.prompt_text(pack, key, arguments)
        mime_type = loaded.manifest.documents[
            loaded.manifest.prompts[key].document
        ].mime_type
    elif kind == "schema":
        value = service.schema(pack, key)
        mime_type = "application/schema+json"
    elif kind == "document":
        value = service.document(pack, key)
        mime_type = loaded.manifest.documents[key].mime_type
    else:
        raise ValueError("kind must be 'document', 'prompt', or 'schema'")
    return content_response(loaded, kind, key, value, mime_type)

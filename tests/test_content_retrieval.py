from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from ohdsi_prompt_registry.catalogue import PromptPackCatalogue
from ohdsi_prompt_registry.content import (
    MAX_CONTENT_BYTES,
    MAX_REFERENCE_LINKS,
    get_content,
)
from ohdsi_prompt_registry.service import PromptRegistryService
from ohdsi_prompt_registry.sources import BundledSource, FilesystemSource


@pytest.fixture
def service() -> PromptRegistryService:
    return PromptRegistryService(PromptPackCatalogue([BundledSource()]))


@pytest.fixture
def filesystem_pack(tmp_path: Path) -> Path:
    source = (
        Path(__file__).parents[1] / "src/ohdsi_prompt_registry/packs/user-elicitation"
    )
    target = tmp_path / "user-elicitation"
    shutil.copytree(source, target)
    return target


def test_default_loads_only_core(service):
    with patch.object(
        service.registry, "document_data", wraps=service.registry.document_data
    ) as read:
        response = get_content(service, "user-elicitation")
    assert read.call_count == 1
    assert read.call_args.args[1] == "instructions"
    assert response["complete"] is True
    assert response["source"] == "bundled"
    assert response["version"] == "1.1"
    assert response["kind"] == "document"
    assert (
        response["content_id"]
        == "sha256:" + hashlib.sha256(response["content"].encode("utf-8")).hexdigest()
    )
    assert {item["key"] for item in response["references"]} == {
        "orientation",
        "answer_changes",
        "client_adapters",
        "examples",
    }
    assert "# Elicitation versus workflow ownership" not in response["content"]


@pytest.mark.parametrize(
    "pack,key,kind",
    [
        ("user-elicitation", "elicit", "prompt"),
        ("user-elicitation", "request", "schema"),
        ("workflow-management", "orientation", "document"),
        ("ohdsi-question-templates", "structure_question", "prompt"),
        ("ohdsi-question-templates", "catalogue", "document"),
    ],
)
def test_content_matches_existing_readers(service, pack, key, kind):
    response = get_content(service, pack, key, kind)
    readers = {
        "document": service.document,
        "schema": service.schema,
        "prompt": service.prompt_text,
    }
    assert response["content"] == readers[kind](pack, key)
    assert response["complete"] is True


def test_prompt_arguments_match_invocation(service):
    arguments = {"request": '{"goal":"What detail do you need?"}'}
    response = get_content(service, "user-elicitation", "elicit", "prompt", arguments)
    assert response["content"] == service.prompt_text(
        "user-elicitation", "elicit", arguments
    )
    assert (
        response["content_id"]
        != get_content(service, "user-elicitation", "elicit", "prompt")["content_id"]
    )


@pytest.mark.parametrize(
    "options",
    [
        {"pack": "missing"},
        {"pack": "user-elicitation", "key": "../orientation.md"},
        {"pack": "user-elicitation", "key": "missing", "kind": "schema"},
        {"pack": "user-elicitation", "key": "missing", "kind": "prompt"},
        {"pack": "user-elicitation", "kind": "all"},
        {"pack": "user-elicitation", "arguments": {}},
        {
            "pack": "user-elicitation",
            "key": "elicit",
            "kind": "prompt",
            "arguments": {"unknown": "x"},
        },
        {
            "pack": "user-elicitation",
            "key": "elicit",
            "kind": "prompt",
            "arguments": {"request": 1},
        },
    ],
)
def test_invalid_selection_is_rejected(service, options):
    with pytest.raises(ValueError):
        get_content(service, **options)


def test_override_and_edits_are_current(filesystem_pack):
    service = PromptRegistryService(
        PromptPackCatalogue([BundledSource(), FilesystemSource(filesystem_pack.parent)])
    )
    before = get_content(service, "user-elicitation")
    (filesystem_pack / "instructions.md").write_text(
        "Changed core — current on next read."
    )
    after = get_content(service, "user-elicitation")
    assert before["source"] == after["source"] == "filesystem"
    assert before["content_id"] != after["content_id"]
    assert after["content"] == "Changed core — current on next read."
    assert len(service.registry.shadows) == 1


def test_oversize_is_not_truncated(filesystem_pack):
    (filesystem_pack / "instructions.md").write_text("é" * MAX_CONTENT_BYTES)
    service = PromptRegistryService(
        PromptPackCatalogue([FilesystemSource(filesystem_pack.parent)])
    )
    response = get_content(service, "user-elicitation")
    assert response["complete"] is False
    assert response["content"] is None
    assert response["error"]["code"] == "CONTENT_TOO_LARGE"
    assert response["content_bytes"] == 2 * MAX_CONTENT_BYTES
    assert response["references"] == []


def test_reference_index_is_bounded(filesystem_pack):
    path = filesystem_pack / "manifest.yaml"
    manifest = yaml.safe_load(path.read_text())
    for index in range(MAX_REFERENCE_LINKS + 5):
        manifest["documents"][f"topic_{index}"] = {
            "path": "orientation.md",
            "mime_type": "text/markdown",
            "description": f"Topic {index}",
        }
    path.write_text(yaml.safe_dump(manifest))
    service = PromptRegistryService(
        PromptPackCatalogue([FilesystemSource(filesystem_pack.parent)])
    )
    response = get_content(service, "user-elicitation")
    assert len(response["references"]) == MAX_REFERENCE_LINKS
    assert response["references_omitted"] == 9

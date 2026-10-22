from pathlib import Path

import pytest
import yaml

from ohdsi_prompt_registry.catalogue import PromptPackCatalogue
from ohdsi_prompt_registry.service import PromptRegistryService
from ohdsi_prompt_registry.sources import FilesystemSource


def _write_pack(
    root: Path,
    placeholder: str,
    *,
    mime_type: str = "text/markdown",
) -> None:
    pack = root / "placeholder-pack"
    pack.mkdir()
    (pack / "instructions.md").write_text(placeholder, encoding="utf-8")
    (pack / "schema.json").write_text(
        '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object"}',
        encoding="utf-8",
    )
    (pack / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "placeholder-pack",
                "title": "Placeholder pack",
                "version": "1",
                "shareability": "public",
                "scope_summary": "Fixture",
                "documents": {
                    "instructions": {
                        "path": "instructions.md",
                        "mime_type": mime_type,
                        "description": "Fixture",
                    }
                },
                "schemas": {
                    "contract": {"path": "schema.json", "description": "Fixture"}
                },
            }
        ),
        encoding="utf-8",
    )


def test_unknown_and_unresolved_placeholders_are_rejected(tmp_path: Path) -> None:
    _write_pack(tmp_path, "{{future:value}}")
    unknown = PromptPackCatalogue([FilesystemSource(tmp_path)])
    assert "unrecognised placeholder" in unknown.rejections[0].reason

    (tmp_path / "placeholder-pack" / "instructions.md").write_text(
        "{{schema:missing}}", encoding="utf-8"
    )
    unresolved = PromptPackCatalogue([FilesystemSource(tmp_path)])
    assert "undeclared schema" in unresolved.rejections[0].reason


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        ('{"outer":{"inner":{"value":28}}}', {"outer": {"inner": {"value": 28}}}),
        (
            "diagnosis: {failure_rates_pct: {reentry: 28}}\n",
            {"diagnosis": {"failure_rates_pct": {"reentry": 28}}},
        ),
    ],
    ids=["nested-json", "yaml-flow-mappings"],
)
def test_structured_documents_with_adjacent_braces_load(
    tmp_path: Path, document: str, expected: dict
) -> None:
    _write_pack(
        tmp_path,
        document,
        mime_type="application/json",
    )

    catalogue = PromptPackCatalogue([FilesystemSource(tmp_path)])

    assert catalogue.rejections == []
    service = PromptRegistryService(catalogue)
    assert service.document("placeholder-pack", "instructions") == expected


def test_brace_sequences_in_structured_string_values_remain_data(
    tmp_path: Path,
) -> None:
    _write_pack(
        tmp_path,
        '{"value":"{{schema:contract}} {{malformed}}"}\n',
        mime_type="application/json",
    )

    catalogue = PromptPackCatalogue([FilesystemSource(tmp_path)])

    assert catalogue.rejections == []
    service = PromptRegistryService(catalogue)
    assert service.document("placeholder-pack", "instructions") == {
        "value": "{{schema:contract}} {{malformed}}"
    }


def test_invalid_structured_document_is_still_rejected(tmp_path: Path) -> None:
    _write_pack(
        tmp_path,
        "diagnosis: {failure_rates_pct: [unterminated}\n",
        mime_type="application/json",
    )

    catalogue = PromptPackCatalogue([FilesystemSource(tmp_path)])

    assert catalogue.all() == ()
    assert "not valid YAML or JSON" in catalogue.rejections[0].reason


def test_malformed_textual_placeholder_is_rejected(tmp_path: Path) -> None:
    _write_pack(tmp_path, "A literal brace: {{schema:contract}\n")

    catalogue = PromptPackCatalogue([FilesystemSource(tmp_path)])

    assert catalogue.all() == ()
    assert "malformed placeholder syntax" in catalogue.rejections[0].reason


@pytest.mark.parametrize("mime_type", ["text/markdown", "text/plain"])
def test_valid_textual_schema_placeholder_expands(
    tmp_path: Path, mime_type: str
) -> None:
    _write_pack(tmp_path, "Contract:\n{{schema:contract}}\n", mime_type=mime_type)
    pack = tmp_path / "placeholder-pack"
    manifest_path = pack / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["schemas"]["contract"]["path"] = "schema.json"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    catalogue = PromptPackCatalogue([FilesystemSource(tmp_path)])

    assert catalogue.rejections == []
    service = PromptRegistryService(catalogue)
    assert '"type": "object"' in service.document(
        "placeholder-pack", "instructions"
    )

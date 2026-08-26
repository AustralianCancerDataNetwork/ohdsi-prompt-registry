from pathlib import Path

import yaml

from ohdsi_prompt_registry.catalogue import PromptPackCatalogue
from ohdsi_prompt_registry.sources import FilesystemSource


def _write_pack(root: Path, placeholder: str) -> None:
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
                        "mime_type": "text/markdown",
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

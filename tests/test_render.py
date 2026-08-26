from __future__ import annotations

import json
import shutil
from importlib import resources
from pathlib import Path

import pytest
import yaml

from ohdsi_prompt_registry.catalogue import PromptPackCatalogue
from ohdsi_prompt_registry.manifest import ValueStyleSpec
from ohdsi_prompt_registry.render import render_markdown, render_value
from ohdsi_prompt_registry.service import PromptRegistryService
from ohdsi_prompt_registry.sources import BundledSource, FilesystemSource

GOLDENS = Path(__file__).parent / "goldens"


def _service() -> PromptRegistryService:
    return PromptRegistryService(PromptPackCatalogue([BundledSource()]))


@pytest.mark.parametrize(
    "case",
    [
        "empty_analyses",
        "null_parameter",
        "empty_list",
        "populated_list",
        "multiple_analyses",
    ],
)
def test_markdown_is_byte_identical_to_captured_oqs_output(case: str) -> None:
    rendered = _service().render(
        "ohdsi-question-templates",
        "study_intent",
        (GOLDENS / f"{case}.json").read_text(encoding="utf-8"),
    )
    assert rendered == (GOLDENS / f"{case}.md").read_text(encoding="utf-8")


def test_value_styles_cover_null_empty_and_populated_lists() -> None:
    styles = ValueStyleSpec(
        null_text="missing",
        empty_list_text="empty",
        list_separator=" / ",
        item_style="code",
    )
    assert render_value(None, styles) == "missing"
    assert render_value([], styles) == "empty"
    assert render_value(["one", "two"], styles) == "`one` / `two`"


def test_no_mapped_parameter_fallback_is_declarative() -> None:
    service = _service()
    pack = service.registry.require("ohdsi-question-templates")
    spec = pack.manifest.render["study_intent"].markdown
    document = json.loads((GOLDENS / "null_parameter.json").read_text())

    rendered = render_markdown(spec, document, {"catalogue": {"templates": {}}})
    assert (
        "| _No mapped parameters for this template_ | _Not specified_ |" in rendered
    )


def test_invalid_document_returns_errors_and_no_markdown() -> None:
    result = _service().render(
        "ohdsi-question-templates",
        "study_intent",
        '{"analyses":[{"analytics_type":"wrong"}]}',
    )
    assert isinstance(result, dict)
    assert result["valid"] is False
    assert "markdown" not in result


def _copy_reference_pack(tmp_path: Path) -> tuple[Path, Path]:
    bundled = resources.files("ohdsi_prompt_registry.packs").joinpath(
        "ohdsi-question-templates"
    )
    root = tmp_path / "packs"
    target = root / "ohdsi-question-templates"
    shutil.copytree(Path(str(bundled)), target)
    return root, target


def _mutate_manifest(target: Path, mutation) -> None:
    path = target / "manifest.yaml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutation(manifest)
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda manifest: manifest["render"]["study_intent"].update(
                {"schema": "undeclared"}
            ),
            "undeclared schema",
        ),
        (
            lambda manifest: manifest["render"]["study_intent"]["markdown"][
                "overview"
            ]["columns"][0].update({"field": "absent_field"}),
            "does not resolve against the schema",
        ),
        (
            lambda manifest: manifest["documents"]["catalogue"].update(
                {"mime_type": "text/markdown"}
            ),
            "must be application/json",
        ),
    ],
)
def test_invalid_render_specs_are_rejected_at_load(
    tmp_path: Path, mutation, reason: str
) -> None:
    root, target = _copy_reference_pack(tmp_path)
    _mutate_manifest(target, mutation)

    catalogue = PromptPackCatalogue([FilesystemSource(root)])
    assert catalogue.all() == ()
    assert reason in catalogue.rejections[0].reason

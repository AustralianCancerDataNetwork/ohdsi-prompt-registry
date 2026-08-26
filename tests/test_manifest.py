import pytest
from pydantic import ValidationError

from ohdsi_prompt_registry.manifest import PackManifest


def _manifest(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "name": "example-pack",
        "title": "Example",
        "version": "1.0",
        "shareability": "public",
        "scope_summary": "Fixture",
        "documents": {},
        "schemas": {},
    }
    value.update(updates)
    return value


def test_manifest_is_strict_and_validates_derived_identifiers() -> None:
    assert PackManifest.model_validate(_manifest()).name == "example-pack"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        PackManifest.model_validate(_manifest(typo=True))
    with pytest.raises(ValidationError, match="lowercase kebab-case"):
        PackManifest.model_validate(_manifest(name="Not_A_Slug"))
    with pytest.raises(ValidationError, match="valid Python identifiers"):
        PackManifest.model_validate(_manifest(documents={"not-valid": {}}))
    with pytest.raises(ValidationError):
        PackManifest.model_validate(_manifest(shareability="secret"))


def test_prompt_declarations_are_text_backed_and_have_explicit_metadata() -> None:
    documents = {
        "instructions": {
            "path": "instructions.md",
            "mime_type": "text/markdown",
            "description": "Instructions",
        }
    }
    prompts = {
        "structure_question": {
            "document": "instructions",
            "title": "Structure a question",
            "description": "Start the workflow.",
            "arguments": {
                "question": {
                    "description": "The initial research question.",
                    "required": False,
                }
            },
        }
    }

    parsed = PackManifest.model_validate(
        _manifest(documents=documents, prompts=prompts, tool_prefix="rqt")
    )
    assert parsed.prompts["structure_question"].arguments["question"].required is False

    with pytest.raises(ValidationError, match="tool_prefix is required"):
        PackManifest.model_validate(_manifest(documents=documents, prompts=prompts))
    with pytest.raises(ValidationError, match="undeclared document"):
        PackManifest.model_validate(
            _manifest(
                documents=documents,
                prompts={
                    "broken": {
                        **prompts["structure_question"],
                        "document": "missing",
                    }
                },
                tool_prefix="rqt",
            )
        )
    with pytest.raises(ValidationError, match="supported text MIME type"):
        PackManifest.model_validate(
            _manifest(
                documents={
                    "catalogue": {
                        "path": "catalogue.yaml",
                        "mime_type": "application/json",
                        "description": "Data",
                    }
                },
                prompts={
                    "broken": {
                        **prompts["structure_question"],
                        "document": "catalogue",
                    }
                },
                tool_prefix="rqt",
            )
        )
    with pytest.raises(ValidationError, match="valid Python identifiers"):
        PackManifest.model_validate(
            _manifest(
                documents=documents,
                prompts={
                    "structure_question": {
                        **prompts["structure_question"],
                        "arguments": {
                            "not-valid": {"description": "Invalid argument name"}
                        },
                    }
                },
                tool_prefix="rqt",
            )
        )

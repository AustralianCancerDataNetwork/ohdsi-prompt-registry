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

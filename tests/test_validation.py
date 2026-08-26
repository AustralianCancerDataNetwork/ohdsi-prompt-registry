import json
from pathlib import Path

from ohdsi_prompt_registry.catalogue import PromptPackCatalogue
from ohdsi_prompt_registry.service import PromptRegistryService
from ohdsi_prompt_registry.sources import BundledSource

GOLDENS = Path(__file__).parent / "goldens"


def _service() -> PromptRegistryService:
    return PromptRegistryService(PromptPackCatalogue([BundledSource()]))


def test_golden_document_validates() -> None:
    result = _service().validate(
        "ohdsi-question-templates",
        "study_intent",
        (GOLDENS / "multiple_analyses.json").read_text(encoding="utf-8"),
    )
    assert result == {"valid": True, "errors": []}


def test_all_schema_errors_have_actionable_locations() -> None:
    document = {
        "analyses": [
            {
                "analytics_type": "wrong_value",
                "template_name": "cohort_method",
            }
        ]
    }
    result = _service().validate(
        "ohdsi-question-templates", "study_intent", json.dumps(document)
    )

    assert result["valid"] is False
    assert {error["path"] for error in result["errors"]} >= {
        "$.analyses[0].analytics_type",
        "$.analyses[0].parameters",
    }
    assert {error["kind"] for error in result["errors"]} == {"schema_violation"}


def test_malformed_json_is_distinct_from_a_schema_violation() -> None:
    result = _service().validate(
        "ohdsi-question-templates", "study_intent", '{"analyses": ['
    )

    assert result["valid"] is False
    assert result["errors"][0]["kind"] == "json_parse"
    assert result["errors"][0]["path"].startswith("line 1, column")

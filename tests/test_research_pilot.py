from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from ohdsi_prompt_registry.catalogue import PromptPackCatalogue
from ohdsi_prompt_registry.content import get_content
from ohdsi_prompt_registry.elicitation import validate_elicitation_response
from ohdsi_prompt_registry.service import PromptRegistryService
from ohdsi_prompt_registry.sources import BundledSource, FilesystemSource

ROOT = Path(__file__).parents[1]
PACK = ROOT / "src/ohdsi_prompt_registry/packs/ohdsi-question-templates"
CATALOGUE = yaml.safe_load((PACK / "catalogue.yaml").read_text())["templates"]
COUNTEREXAMPLES = json.loads(
    (Path(__file__).parent / "fixtures/research-pilot-counterexamples.json").read_text()
)
NAME = "ohdsi-question-templates"


@pytest.fixture
def service() -> PromptRegistryService:
    return PromptRegistryService(PromptPackCatalogue([BundledSource()]))


@pytest.fixture
def examples(service):
    return service.document(NAME, "pilot_examples")


@pytest.fixture
def overridden_pack(tmp_path):
    pack = tmp_path / NAME
    shutil.copytree(PACK, pack)
    return pack


def complete_intent(template_name: str) -> dict:
    template = CATALOGUE[template_name]
    parameters = {
        field: ["Treatment supplied by the user"]
        if field == "treatment_cohorts"
        else f"User-supplied {field}"
        for field in template["required_parameters"]
    }
    return {
        "analyses": [
            {
                "analytics_type": template["analytics_type"],
                "template_name": template_name,
                "parameters": parameters,
            }
        ]
    }


def assert_research_pack_consistent(catalogue, draft, final):
    """Author check for duplicated pack declarations; never used at runtime."""
    templates = catalogue["templates"]
    definitions = draft["$defs"]
    known = definitions["Parameters"]["properties"]
    assert catalogue["total"] == len(templates)
    assert set(templates) == set(definitions["TemplateName"]["enum"])
    for name, definition in definitions.items():
        assert final["$defs"][name] == definition, name
    branches = final["properties"]["analyses"]["items"]["allOf"]
    by_name = {
        branch["if"]["properties"]["template_name"]["const"]: branch
        for branch in branches
    }
    assert len(branches) == len(by_name) == len(templates)
    assert set(by_name) == set(templates)
    for name, template in templates.items():
        required = template["required_parameters"]
        nullable = template.get("nullable_parameters", [])
        assert required and len(required) == len(set(required))
        assert set(required) <= known.keys()
        assert len(nullable) == len(set(nullable)) and set(nullable) <= set(required)
        assert template["analytics_type"] in definitions["AnalyticsType"]["enum"]
        expected = {}
        for field, specification in known.items():
            types = [
                branch["type"]
                for branch in specification["anyOf"]
                if branch["type"] != "null"
            ]
            assert types in (["string"], ["array"])
            definition = "TextList" if types == ["array"] else "Text"
            if field not in required:
                definition = "Unused"
            elif field in nullable:
                assert types == ["string"]
                definition = "NullableText"
            expected[field] = {"$ref": f"#/$defs/{definition}"}
        assert by_name[name] == {
            "if": {"properties": {"template_name": {"const": name}}},
            "then": {
                "properties": {
                    "analytics_type": {"const": template["analytics_type"]},
                    "parameters": {
                        "required": required,
                        "additionalProperties": False,
                        "properties": expected,
                    },
                }
            },
        }, name


def test_bundled_final_schema_and_catalogue_agree(service):
    assert not service.registry.rejections
    assert_research_pack_consistent(
        service.document(NAME, "catalogue"),
        service.schema(NAME, "study_intent"),
        service.schema(NAME, "study_intent_final"),
    )


@pytest.mark.parametrize(
    "change", ["required", "nullable", "analytics", "names", "total"]
)
def test_author_check_catches_catalogue_drift(service, change):
    catalogue = copy.deepcopy(service.document(NAME, "catalogue"))
    template = catalogue["templates"]["outcome_incidence"]
    if change == "required":
        template["required_parameters"].append("comparator_cohort")
    elif change == "nullable":
        template["nullable_parameters"] = ["time_at_risk"]
    elif change == "analytics":
        template["analytics_type"] = "effect_estimation"
    elif change == "names":
        del catalogue["templates"]["outcome_incidence"]
    else:
        catalogue["total"] += 1
    with pytest.raises(AssertionError):
        assert_research_pack_consistent(
            catalogue,
            service.schema(NAME, "study_intent"),
            service.schema(NAME, "study_intent_final"),
        )


def test_author_check_catches_final_schema_drift(service):
    schema = service.schema(NAME, "study_intent_final")
    schema["properties"]["analyses"]["items"]["allOf"][0]["then"]["properties"][
        "parameters"
    ]["properties"]["target_cohort"] = {"$ref": "#/$defs/Unused"}
    with pytest.raises(AssertionError):
        assert_research_pack_consistent(
            service.document(NAME, "catalogue"),
            service.schema(NAME, "study_intent"),
            schema,
        )


def test_final_renderer_matches_draft_except_schema_and_null_text(service):
    manifest = service.manifest(NAME)
    expected = copy.deepcopy(manifest["render"]["study_intent"])
    expected["schema"] = "study_intent_final"
    expected["markdown"]["value_styles"]["null_text"] = "_None (intentional)_"
    assert manifest["render"]["study_intent_final"] == expected


def test_override_catalogue_and_schema_are_updated_together(overridden_pack, examples):
    overridden = PromptRegistryService(
        PromptPackCatalogue([BundledSource(), FilesystemSource(overridden_pack.parent)])
    )
    assert overridden.registry.require(NAME).source == "filesystem"
    assert not overridden.registry.rejections
    document = examples["missing_parameter"]["final"]
    catalogue = overridden.document(NAME, "catalogue")
    catalogue["templates"]["outcome_incidence"]["required_parameters"].append(
        "comparator_cohort"
    )
    (overridden_pack / "catalogue.yaml").write_text(yaml.safe_dump(catalogue))
    # The schema is authoritative: editing only the catalogue is insufficient.
    assert overridden.validate(NAME, "study_intent_final", document)["valid"]
    schema = overridden.schema(NAME, "study_intent_final")
    with pytest.raises(AssertionError):
        assert_research_pack_consistent(
            catalogue, overridden.schema(NAME, "study_intent"), schema
        )
    branch = next(
        branch
        for branch in schema["properties"]["analyses"]["items"]["allOf"]
        if branch["if"]["properties"]["template_name"]["const"] == "outcome_incidence"
    )
    parameters = branch["then"]["properties"]["parameters"]
    parameters["required"].append("comparator_cohort")
    parameters["properties"]["comparator_cohort"] = {"$ref": "#/$defs/Text"}
    (overridden_pack / "study-intent-final.schema.json").write_text(json.dumps(schema))
    assert_research_pack_consistent(
        catalogue, overridden.schema(NAME, "study_intent"), schema
    )
    checked = overridden.validate(NAME, "study_intent_final", document)
    assert not checked["valid"]
    assert overridden.render(NAME, "study_intent_final", document) == checked
    assert "$.analyses[0].parameters.comparator_cohort" in {
        error["path"] for error in checked["errors"]
    }
    document["analyses"][0]["parameters"]["comparator_cohort"] = (
        "User-supplied comparator"
    )
    assert overridden.validate(NAME, "study_intent_final", document)["valid"]
    assert "User-supplied comparator" in overridden.render(
        NAME, "study_intent_final", document
    )


def test_effective_final_schema_edits_apply_to_validate_and_render(overridden_pack):
    overridden = PromptRegistryService(
        PromptPackCatalogue([BundledSource(), FilesystemSource(overridden_pack.parent)])
    )
    document = complete_intent("patient_characterization")
    assert overridden.validate(NAME, "study_intent_final", document)["valid"]
    schema = overridden.schema(NAME, "study_intent_final")
    schema["$defs"]["Text"]["minLength"] = 100
    (overridden_pack / "study-intent-final.schema.json").write_text(json.dumps(schema))
    checked = overridden.validate(NAME, "study_intent_final", document)
    assert not checked["valid"]
    assert overridden.render(NAME, "study_intent_final", document) == checked
    assert overridden.validate(NAME, "study_intent", document)["valid"]


def test_rejected_override_leaves_the_bundled_pair_active(overridden_pack, service):
    (overridden_pack / "study-intent-final.schema.json").write_text(
        '{"type":"invalid"}'
    )
    overridden = PromptRegistryService(
        PromptPackCatalogue([BundledSource(), FilesystemSource(overridden_pack.parent)])
    )
    assert overridden.registry.require(NAME).source == "bundled"
    assert len(overridden.registry.rejections) == 1
    assert overridden.schema(NAME, "study_intent_final") == service.schema(
        NAME, "study_intent_final"
    )
    assert overridden.document(NAME, "catalogue") == service.document(NAME, "catalogue")


@pytest.mark.parametrize(
    "document",
    [
        "{invalid",
        "null",
        "[]",
        '"text"',
        "1",
        '{"analyses":[{"analytics_type":"characterization","template_name":"patient_characterization","parameters":{"target_cohort":42}}]}',
    ],
)
def test_invalid_structure_returns_errors_without_entering_domain_checks(
    service, document
):
    checked = service.validate(NAME, "study_intent_final", document)
    assert not checked["valid"]
    assert service.render(NAME, "study_intent_final", document) == checked


@pytest.mark.parametrize("case", COUNTEREXAMPLES, ids=lambda case: case["name"])
def test_assessed_counterexamples_remain_drafts_but_cannot_render_as_final(
    service, case
):
    document = case["document"]
    assert service.validate(NAME, "study_intent", document)["valid"]
    checked = service.validate(NAME, "study_intent_final", document)
    assert not checked["valid"]
    assert service.render(NAME, "study_intent_final", document) == checked


@pytest.mark.parametrize("template_name", CATALOGUE)
def test_all_catalogue_templates_validate_and_render_through_final_contract(
    service, template_name
):
    document = complete_intent(template_name)
    assert service.validate(NAME, "study_intent_final", document) == {
        "valid": True,
        "errors": [],
    }
    rendered = service.render(NAME, "study_intent_final", document)
    assert isinstance(rendered, str)
    assert rendered == service.render(NAME, "study_intent", document)


@pytest.mark.parametrize("template_name", CATALOGUE)
def test_final_contract_enforces_pairing_and_every_required_parameter(
    service, template_name
):
    document = complete_intent(template_name)
    analysis = document["analyses"][0]
    original_type = analysis["analytics_type"]
    analysis["analytics_type"] = (
        "effect_estimation"
        if original_type == "characterization"
        else "characterization"
    )
    assert not service.validate(NAME, "study_intent_final", document)["valid"]
    analysis["analytics_type"] = original_type
    for field in CATALOGUE[template_name]["required_parameters"]:
        value = analysis["parameters"].pop(field)
        checked = service.validate(NAME, "study_intent_final", document)
        assert not checked["valid"], field
        assert (
            sum(
                error["path"] == f"$.analyses[0].parameters.{field}"
                for error in checked["errors"]
            )
            == 1
        )
        analysis["parameters"][field] = None
        assert service.validate(NAME, "study_intent_final", document)["valid"] == (
            field in CATALOGUE[template_name].get("nullable_parameters", [])
        ), field
        analysis["parameters"][field] = value


@pytest.mark.parametrize(
    "template_name,field,value,reason",
    [
        ("patient_characterization", "target_cohort", value, "does not match")
        for value in ("", " ", "\n\t")
    ]
    + [
        ("treatment_patterns", "treatment_cohorts", value, reason)
        for value, reason in (
            ([], "non-empty"),
            ([""], "does not match"),
            ([" \t"], "does not match"),
            (["A", "A"], "non-unique"),
        )
    ],
)
def test_final_values_need_nonblank_text_or_nonempty_distinct_lists(
    service, template_name, field, value, reason
):
    document = complete_intent(template_name)
    document["analyses"][0]["parameters"][field] = value
    checked = service.validate(NAME, "study_intent_final", document)
    assert not checked["valid"]
    assert any(
        error["path"].startswith(f"$.analyses[0].parameters.{field}")
        and reason in error["reason"]
        for error in checked["errors"]
    )


def test_nonapplicable_parameters_cannot_hide_values_outside_the_rendered_template(
    service,
):
    document = complete_intent("patient_characterization")
    parameters = document["analyses"][0]["parameters"]
    parameters["outcome_cohort"] = "A leftover outcome from another template"
    assert not service.validate(NAME, "study_intent_final", document)["valid"]
    parameters["outcome_cohort"] = None
    parameters["nesting_cohort"] = None
    assert service.validate(NAME, "study_intent_final", document)["valid"]
    assert "_None (intentional)_" not in service.render(
        NAME, "study_intent_final", document
    )


@pytest.mark.parametrize("location", ["root", "analysis", "parameters"])
def test_unknown_fields_cannot_masquerade_as_approval(service, location):
    document = complete_intent("patient_characterization")
    containers = {
        "root": document,
        "analysis": document["analyses"][0],
        "parameters": document["analyses"][0]["parameters"],
    }
    containers[location]["approved"] = [42, {"unexpected": "value"}]
    assert not service.validate(NAME, "study_intent_final", document)["valid"]


def test_multiple_analyses_are_checked_independently_before_final_rendering(service):
    document = complete_intent("patient_characterization")
    document["analyses"].extend(complete_intent("cohort_method")["analyses"])
    rendered = service.render(NAME, "study_intent_final", document)
    assert "Total analyses: **2**" in rendered
    del document["analyses"][1]["parameters"]["comparator_cohort"]
    checked = service.render(NAME, "study_intent_final", document)
    assert not checked["valid"]
    assert "$.analyses[1].parameters.comparator_cohort" in {
        error["path"] for error in checked["errors"]
    }


def test_intentional_nesting_null_and_unused_null_are_supported(service, examples):
    document = examples["intentional_null"]["final"]
    assert service.validate(NAME, "study_intent_final", document)["valid"]
    rendered = service.render(NAME, "study_intent_final", document)
    assert "_None (intentional)_" in rendered
    assert "_Not specified_" not in rendered
    assert "_Not specified_" in service.render(NAME, "study_intent", document)


def test_worked_missing_answer_stays_draft_until_a_value_is_supplied(service, examples):
    case = examples["missing_parameter"]
    assert service.validate(NAME, "study_intent", case["draft"])["valid"]
    assert not service.validate(NAME, "study_intent_final", case["draft"])["valid"]
    assert validate_elicitation_response(service, case["request"], case["answered"])[
        "valid"
    ]
    assert service.validate(NAME, "study_intent_final", case["final"])["valid"]
    assert (
        case["final"]["analyses"][0]["parameters"]["time_at_risk"]
        == case["answered"]["answer"]["text"]
    )


@pytest.mark.parametrize(
    "outcome", ["deferred", "declined", "cancelled", "batch_result"]
)
def test_worked_non_answers_follow_shared_elicitation_contract(
    service, examples, outcome
):
    case = examples["non_answers"]
    request = case["batch_request"] if outcome == "batch_result" else case["request"]
    assert validate_elicitation_response(service, request, case[outcome])["valid"]
    assert case[outcome]["answer"] is None


def test_worked_revision_rejects_mismatched_reply_and_preserves_independent_context(
    service, examples
):
    case = examples["revised_answer"]
    assert not validate_elicitation_response(
        service, case["request"], case["stale_reply"]
    )["valid"]
    assert validate_elicitation_response(
        service, case["request"], case["current_reply"]
    )["valid"]
    context = case["context"]
    assert service.validate("workflow-management", "context", context)["valid"]
    assert context["pending_requests"]["a1-time-at-risk"]["revision"] == 2
    assert context["artifacts"]["final_intent"]["status"] == "stale"
    assert context["artifacts"]["characterization_draft"]["status"] == "ready"
    # A matching old pair is still valid in isolation: active-revision ownership is external.
    old = examples["missing_parameter"]
    assert validate_elicitation_response(service, old["request"], case["stale_reply"])[
        "valid"
    ]


def test_pilot_prompt_loads_only_its_selected_core_and_preserves_arguments(service):
    arguments = {
        "question": "Use the population already supplied.",
        "mode": "batch",
        "presentation": "text",
        "draft": '{"analyses":[]}',
    }
    with patch.object(
        service.registry, "document_data", wraps=service.registry.document_data
    ) as read:
        response = get_content(
            service, NAME, "structure_question_pilot", "prompt", arguments
        )
    assert read.call_count == 1
    assert read.call_args.args[1] == "pilot_instructions"
    assert response["complete"] is True
    assert response["content"] == service.prompt_text(
        NAME, "structure_question_pilot", arguments
    )
    assert "# User-provided starting inputs" in response["content"]
    assert "Use the population already supplied." in response["content"]
    assert "# User elicitation" not in response["content"]
    assert "# Workflow management" not in response["content"]
    assert any(item["key"] == "pilot_examples" for item in response["references"])


def test_legacy_default_instructions_and_draft_schema_are_unchanged(service):
    instructions = service.document(NAME, "instructions")
    assert instructions.startswith("Your goal is to translate clinical questions")
    assert service.prompt_text(NAME, "structure_question") == instructions
    assert service.document(NAME, "pilot_instructions").startswith(
        "# Research-question pilot"
    )
    # Completeness checks do not change the existing draft schema.
    draft = json.loads((PACK / "study-intent.schema.json").read_text())
    assert "additionalProperties" not in draft
    assert "minItems" not in draft["properties"]["analyses"]

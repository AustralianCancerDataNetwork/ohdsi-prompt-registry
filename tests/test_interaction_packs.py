from __future__ import annotations

import copy

import pytest

from ohdsi_prompt_registry.catalogue import PromptPackCatalogue
from ohdsi_prompt_registry.elicitation import validate_elicitation_response
from ohdsi_prompt_registry.service import PromptRegistryService
from ohdsi_prompt_registry.sources import BundledSource


@pytest.fixture
def service() -> PromptRegistryService:
    return PromptRegistryService(PromptPackCatalogue([BundledSource()]))


@pytest.fixture
def pair(service):
    return copy.deepcopy(service.document("user-elicitation", "examples")["choice"])


def test_worked_pairs_validate(service):
    for pair in service.document("user-elicitation", "examples").values():
        assert validate_elicitation_response(service, **pair) == {
            "valid": True,
            "errors": [],
        }


def test_workflow_context_validates(service):
    examples = service.document("workflow-management", "examples")
    assert service.validate(
        "workflow-management", "context", examples["pending_comparison"]
    )["valid"]
    changed = copy.deepcopy(examples["pending_comparison"])
    changed["pending_requests"]["comparison-1"]["required_for"] = "finalize"
    assert not service.validate("workflow-management", "context", changed)["valid"]


@pytest.mark.parametrize("key,value", [("request_id", "other"), ("revision", 2)])
def test_mismatched_identity_fails(service, pair, key, value):
    pair["result"][key] = value
    assert service.validate("user-elicitation", "request", pair["request"])["valid"]
    assert service.validate("user-elicitation", "result", pair["result"])["valid"]
    checked = validate_elicitation_response(service, **pair)
    assert not checked["valid"]
    assert checked["errors"][0]["path"] == f"$.result.{key}"


def test_unknown_choice_fails(service, pair):
    pair["result"]["answer"]["choice_id"] = "not-offered"
    assert not validate_elicitation_response(service, **pair)["valid"]


def test_duplicate_choice_ids_fail(service, pair):
    pair["request"]["answer_spec"]["choices"][1]["id"] = "a"
    assert not validate_elicitation_response(service, **pair)["valid"]


def test_free_text_policy_is_enforced(service, pair):
    pair["result"]["answer"] = {"kind": "text", "text": "Something else"}
    assert validate_elicitation_response(service, **pair)["valid"]
    pair["request"]["answer_spec"]["allow_free_text"] = False
    assert not validate_elicitation_response(service, **pair)["valid"]


def test_choice_cannot_answer_text_request(service, pair):
    pair["request"]["answer_spec"] = {"kind": "text"}
    assert not validate_elicitation_response(service, **pair)["valid"]


@pytest.mark.parametrize(
    "change",
    [
        {"status": "pending"},
        {"status": "declined", "answer": None, "source": "none", "reason": "closed"},
        {"answer": None},
        {"answer": {"kind": "text", "text": "   "}},
        {"contract_version": "2.0"},
        {"status": "unresolved", "answer": None, "reason": None},
        {"invented": True},
    ],
)
def test_invalid_results_fail(service, pair, change):
    pair["result"].update(change)
    assert not validate_elicitation_response(service, **pair)["valid"]


@pytest.mark.parametrize("key", ["request", "result"])
def test_parse_errors_are_reported(service, pair, key):
    pair[key] = "{invalid"
    checked = validate_elicitation_response(service, **pair)
    assert not checked["valid"]
    assert checked["errors"][0]["kind"] == "json_parse"
    assert checked["errors"][0]["path"] == f"$.{key}"


@pytest.mark.parametrize("value", ["null", "[]", '"text"', "1"])
def test_non_object_documents_fail(service, pair, value):
    pair["request"] = value
    assert not validate_elicitation_response(service, **pair)["valid"]


@pytest.mark.parametrize(
    "change",
    [
        {"contract_version": "2.0"},
        {"goal": "   "},
        {"revision": 0},
        {"policy": {"unsupported_setting": True}},
    ],
)
def test_invalid_requests_fail(service, pair, change):
    pair["request"].update(change)
    assert not validate_elicitation_response(service, **pair)["valid"]


def test_standalone_has_no_workflow_requirement(service):
    pair = service.document("user-elicitation", "examples")["standalone_text"]
    assert "workflow_id" not in pair["request"]
    assert validate_elicitation_response(service, **pair)["valid"]


def test_discovery_does_not_apply_everywhere(service):
    assert {p["name"] for p in service.catalogue(["interaction"])["packs"]} == {
        "user-elicitation",
        "workflow-management",
    }
    assert not service.catalogue(["unrelated-tag"])["packs"]

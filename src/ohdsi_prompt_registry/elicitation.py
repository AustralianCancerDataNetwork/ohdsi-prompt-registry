"""Request/result checks that cannot be expressed by two standalone schemas."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ohdsi_prompt_registry.validation import parse_candidate

if TYPE_CHECKING:
    from ohdsi_prompt_registry.service import PromptRegistryService


def validate_elicitation_response(
    service: PromptRegistryService,
    request: str | dict[str, Any],
    result: str | dict[str, Any],
) -> dict[str, Any]:
    """Check effective pack schemas, then request identity and answer constraints.

    Current revision, replay handling, domain suitability, and workflow readiness
    remain caller responsibilities. This function does not collect user input.
    """
    documents: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    for key, value in (("request", request), ("result", result)):
        parsed, parse_error = parse_candidate(value)
        if parse_error:
            error = parse_error["errors"][0]
            error["reason"] += f" ({error['path']})"
            error["path"] = "$"
        validation = parse_error or service.validate("user-elicitation", key, value)
        errors.extend(
            {**error, "path": f"$.{key}{error['path'].removeprefix('$')}"}
            for error in validation["errors"]
        )
        documents[key] = parsed
    if not errors:
        errors = _pair_errors(documents["request"], documents["result"])
    return {"valid": not errors, "errors": errors}


def _pair_errors(
    request: dict[str, Any], result: dict[str, Any]
) -> list[dict[str, str]]:
    issues = [
        (f"$.result.{key}", f"Must match request {key}.")
        for key in ("request_id", "revision")
        if request[key] != result[key]
    ]
    spec = request["answer_spec"]
    choice_ids = [choice["id"] for choice in spec.get("choices", [])]
    if len(choice_ids) != len(set(choice_ids)):
        issues.append(("$.request.answer_spec.choices", "Choice IDs must be unique."))
    answer = result["answer"]
    if answer is not None:
        issues.extend(_answer_errors(spec, answer, choice_ids))
    return [
        {"path": path, "reason": reason, "kind": "request_mismatch"}
        for path, reason in issues
    ]


def _answer_errors(
    spec: dict[str, Any], answer: dict[str, Any], choice_ids: list[str]
) -> list[tuple[str, str]]:
    if answer["kind"] == "single_choice":
        if spec["kind"] != "single_choice" or answer["choice_id"] not in choice_ids:
            return [
                ("$.result.answer.choice_id", "Choose an ID offered by this request.")
            ]
    elif spec["kind"] == "single_choice" and not spec["allow_free_text"]:
        return [("$.result.answer", "This request does not allow a free-text answer.")]
    return []

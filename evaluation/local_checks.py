"""Local installed-artifact MCP/retrieval checks. Does not call a model."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

SELECTIONS = (
    {
        "pack": "ohdsi-question-templates",
        "kind": "prompt",
        "key": "structure_question_pilot",
    },
    {"pack": "user-elicitation"},
    {"pack": "workflow-management"},
    {"pack": "ohdsi-question-templates", "key": "catalogue"},
)


def structured(result: CallToolResult) -> dict[str, Any]:
    assert not result.isError
    assert result.structuredContent is not None
    return result.structuredContent


async def selected_sample(session: ClientSession, selection: dict, warm: int) -> dict:
    started = time.perf_counter()
    result = await session.call_tool("ohdsi_prompt_registry_get", selection)
    seconds = time.perf_counter() - started
    assert not result.isError
    body = result.structuredContent
    assert body is not None and body["complete"]
    assert body["source"] == "bundled"
    assert (
        body["version"]
        == {
            "ohdsi-question-templates": "1.3",
            "user-elicitation": "1.1",
            "workflow-management": "1.0",
        }[body["pack"]]
    )
    assert body["key"] == selection.get("key", "instructions")
    content = body["content"]
    return {
        "selection": selection,
        "warm_index": warm,
        "seconds": seconds,
        **{
            key: body[key]
            for key in (
                "pack",
                "version",
                "source",
                "key",
                "kind",
                "content_id",
                "content_bytes",
            )
        },
        "characters": len(content)
        if isinstance(content, str)
        else len(json.dumps(content, ensure_ascii=False)),
    }


async def protocol_cases(session: ClientSession, root: Path) -> list[dict]:
    observations = []
    cases = json.loads(
        (root / "tests/fixtures/research-pilot-counterexamples.json").read_text()
    )
    for case in cases:
        arguments = {
            "pack": "ohdsi-question-templates",
            "document": json.dumps(case["document"]),
        }
        checked = await session.call_tool(
            "ohdsi_prompt_registry_validate",
            {**arguments, "schema": "study_intent_final"},
        )
        rendered = await session.call_tool(
            "ohdsi_prompt_registry_render",
            {**arguments, "render": "study_intent_final"},
        )
        assert structured(checked)["valid"] is False
        assert structured(rendered)["result"]["valid"] is False
        observations.append(
            {
                "scenario": case["name"],
                "final_validation": "rejected",
                "final_rendering": "rejected",
            }
        )
    pair_data = await session.call_tool(
        "ohdsi_prompt_registry_get", {"pack": "user-elicitation", "key": "examples"}
    )
    pair = structured(pair_data)["content"]["choice"]
    pair["result"]["request_id"] = "wrong"
    pair["result"]["revision"] += 1
    pair["result"]["answer"]["choice_id"] = "unoffered"
    checked = await session.call_tool(
        "ohdsi_prompt_registry_validate_elicitation",
        {key: json.dumps(value) for key, value in pair.items()},
    )
    assert structured(checked)["valid"] is False
    observations.append(
        {"scenario": "mismatched_reply", "errors": structured(checked)["errors"]}
    )
    explicit = await session.call_tool(
        "ohdsi_prompt_registry_get", {"pack": "user-elicitation", "key": "orientation"}
    )
    assert structured(explicit)["complete"]
    return observations


async def process_run(
    parameters: StdioServerParameters, root: Path, repetition: int, errlog: Any
) -> dict:
    started = time.perf_counter()
    async with stdio_client(parameters, errlog=errlog) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            initialization_seconds = time.perf_counter() - started
            status = await session.call_tool("ohdsi_prompt_registry_status", {})
            tools = await session.list_tools()
            prompts = await session.list_prompts()
            resources = await session.list_resources()
            names = {tool.name for tool in tools.tools}
            assert {
                "ohdsi_prompt_registry_get",
                "ohdsi_prompt_registry_validate_elicitation",
            } <= names
            assert (
                not {
                    "ohdsi_prompt_registry_validate_study_intent",
                    "ohdsi_prompt_registry_render_study_intent",
                }
                & names
            )
            assert any(
                prompt.name == "rqt_structure_question_pilot"
                for prompt in prompts.prompts
            )
            assert any(
                str(resource.uri).endswith("/schema/study_intent_final")
                for resource in resources.resources
            )
            samples = [
                await selected_sample(session, selection, warm)
                for warm in range(3)
                for selection in SELECTIONS
            ]
            observations = (
                await protocol_cases(session, root) if repetition == 1 else []
            )
            return {
                "repetition": repetition,
                "initialization_seconds": initialization_seconds,
                "server_info": initialized.serverInfo.model_dump(),
                "status": status.structuredContent,
                "tools": sorted(names),
                "prompts": [prompt.name for prompt in prompts.prompts],
                "samples": samples,
                "protocol_observations": observations,
            }


async def exercise(python: Path, installed: Path, output: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    groundworkers = root.parents[1] / "groundworkers" / "src"
    parameters = StdioServerParameters(
        command=str(python),
        args=[str(root / "evaluation/serve_registry.py")],
        env={**os.environ, "PYTHONPATH": f"{installed}:{groundworkers}"},
    )
    with output.with_suffix(".stderr").open("w") as errlog:
        runs = [
            await process_run(parameters, root, repetition, errlog)
            for repetition in range(1, 4)
        ]
    generic = [
        sample
        for sample in runs[0]["samples"]
        if sample["warm_index"] == 0
        and sample["pack"] in ("user-elicitation", "workflow-management")
    ]
    summary = {
        "scope": "Installed wheel in real stdio Groundworkers MCP processes; no model, UI, or conversation adherence evidence",
        "cold_processes": 3,
        "retrieval_calls": sum(len(run["samples"]) for run in runs),
        "optional_reference_bodies_in_routine_retrieval": 0,
        "generic_core_bytes": sum(sample["content_bytes"] for sample in generic),
        "generic_core_characters": sum(sample["characters"] for sample in generic),
        "token_measurement": "Tokenizer unavailable; characters and UTF-8 bytes measured, no tokenizer-specific claim",
        "retrieval_median_seconds": statistics.median(
            sample["seconds"] for run in runs for sample in run["samples"]
        ),
        "initialization_median_seconds": statistics.median(
            run["initialization_seconds"] for run in runs
        ),
        "runs": runs,
    }
    output.write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {key: value for key, value in summary.items() if key != "runs"}, indent=2
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(exercise(Path(sys.executable), args.installed, args.output))


if __name__ == "__main__":
    main()

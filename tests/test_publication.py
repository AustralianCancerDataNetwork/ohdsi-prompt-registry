from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import yaml
from groundskeeping.configurator import ConfigWizardController, MutationOperation
from groundskeeping.contracts import ReviewStep
from groundworkers.application.setup.plugin_configuration import (
    PackageConfigMutationService,
)
from groundworkers.base.server import GroundworkersMCPServer
from groundworkers.plugins import PluginConfigResolver, PluginContext
from oa_configurator import (
    CDMDatabaseConfig,
    ConnectionConfig,
    Resolver,
    StackConfig,
    load_stack_config_from_path,
    save_stack_config,
)

from ohdsi_prompt_registry import OhdsiPromptRegistryConfig, plugin
from ohdsi_prompt_registry.plugin import OhdsiPromptRegistryState

EXPECTED_URIS = {
    "prompt-registry://catalogue",
    "prompt-registry://ohdsi-question-templates/manifest",
    "prompt-registry://ohdsi-question-templates/instructions",
    "prompt-registry://ohdsi-question-templates/catalogue",
    "prompt-registry://ohdsi-question-templates/schema/study_intent",
}


def _context() -> PluginContext:
    return PluginContext(
        resolver=PluginConfigResolver(Resolver(StackConfig.for_session())),
        cdm_database=None,
        cdm_engine=None,
        vector_store=None,
        embedding_backend_factory=None,
        embedding_model_backend_factory=None,
        chat_backend_factory=None,
    )


def _build(config: OhdsiPromptRegistryConfig) -> OhdsiPromptRegistryState:
    state = plugin.build(_context(), config)
    assert state is not None
    return state


def _write_prompt_pack(
    root: Path,
    name: str,
    *,
    prefix: str,
    prompt_key: str = "workflow",
    content: str | None = None,
) -> None:
    pack = root / name
    pack.mkdir(parents=True)
    (pack / "instructions.md").write_text(
        content or f"Instructions from {name}.", encoding="utf-8"
    )
    manifest = {
        "name": name,
        "title": name.title(),
        "version": "1.0",
        "shareability": "public",
        "scope_summary": f"Fixture for {name}",
        "documents": {
            "instructions": {
                "path": "instructions.md",
                "mime_type": "text/markdown",
                "description": "Fixture instructions",
            }
        },
        "schemas": {},
        "prompts": {
            prompt_key: {
                "document": "instructions",
                "title": f"Run {name}",
                "description": f"Run the {name} workflow.",
                "arguments": {},
            }
        },
        "tool_prefix": prefix,
    }
    (pack / "manifest.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8"
    )


def test_real_server_registration_is_exact_and_described() -> None:
    state = _build(OhdsiPromptRegistryConfig())
    server = GroundworkersMCPServer("test")

    @server.tool("comparator_recommender_find_target")
    def find_target() -> None:
        pass

    @server.tool("comparator_recommender_recommend")
    def recommend() -> None:
        pass

    plugin.register(server, state)

    assert set(server.list_resources()) == EXPECTED_URIS
    assert len(server.list_resources()) == len(EXPECTED_URIS)
    descriptions = server.describe_resources()
    assert descriptions[
        "prompt-registry://ohdsi-question-templates/instructions"
    ]["description"].startswith("Canonical guidance")
    assert set(server.list_tools()) >= {
        "ohdsi_prompt_registry_catalogue",
        "ohdsi_prompt_registry_links",
        "ohdsi_prompt_registry_render",
        "ohdsi_prompt_registry_status",
        "ohdsi_prompt_registry_validate",
    }
    assert "rqt_structure_question" in server.list_prompts()
    prompt_description = server.describe_prompts()["rqt_structure_question"]
    assert prompt_description["title"] == "Structure an OHDSI research question"
    assert prompt_description["arguments"] == [
        {
            "name": "question",
            "description": "The clinical research question to structure.",
            "required": False,
        }
    ]

    instructions_reader = server._resources[
        "prompt-registry://ohdsi-question-templates/instructions"
    ][0]
    instructions = instructions_reader()
    assert "{{schema:" not in instructions
    assert '"$schema": "https://json-schema.org/draft/2020-12/schema"' in instructions

    catalogue = server.call("ohdsi_prompt_registry_catalogue")
    assert catalogue["packs"][0]["resource_uris"] == sorted(
        EXPECTED_URIS - {"prompt-registry://catalogue"},
        key=lambda uri: catalogue["packs"][0]["resource_uris"].index(uri),
    )
    links = server.call("ohdsi_prompt_registry_links", "ohdsi-question-templates")
    assert {str(link.uri) for link in links.content} == (
        EXPECTED_URIS - {"prompt-registry://catalogue"}
    )
    assert len(links.structuredContent["links"]) == 4
    assert catalogue["packs"][0]["prompt_keys"] == ["structure_question"]

    prompt = server.call_prompt(
        "rqt_structure_question",
        question="Does semaglutide reduce cardiovascular risk?",
    )
    assert len(prompt) == 1
    prompt_text = prompt[0]["content"]["text"]
    assert "{{schema:" not in prompt_text
    assert '"$schema": "https://json-schema.org/draft/2020-12/schema"' in prompt_text
    assert "# User-provided starting inputs" in prompt_text
    assert "Does semaglutide reduce cardiovascular risk?" in prompt_text
    prompt_without_input = server.call_prompt("rqt_structure_question")
    assert "# User-provided starting inputs" not in (
        prompt_without_input[0]["content"]["text"]
    )


def test_prompt_collisions_are_local_first_wins_and_reported(tmp_path: Path) -> None:
    _write_prompt_pack(tmp_path, "alpha-pack", prefix="shared")
    _write_prompt_pack(tmp_path, "beta-pack", prefix="shared")
    state = _build(
        OhdsiPromptRegistryConfig(
            packs_root=str(tmp_path),
            include_bundled=False,
            include_installed=False,
        )
    )
    server = GroundworkersMCPServer("test")
    plugin.register(server, state)

    assert server.list_prompts() == ["shared_workflow"]
    text = server.call_prompt("shared_workflow")[0]["content"]["text"]
    assert "alpha-pack" in text
    report = plugin.verify_readiness(state).as_dict()
    collision = next(
        field
        for field in report["fields"]
        if field["key"].startswith("prompt_collision_")
    )
    assert collision["state"] == "warning"
    assert collision["value"] == "beta-pack"
    assert "alpha-pack" in collision["detail"]


def test_prompt_registration_does_not_overwrite_a_core_prompt(tmp_path: Path) -> None:
    _write_prompt_pack(
        tmp_path,
        "colliding-pack",
        prefix="normalize",
        prompt_key="clinical_term",
    )
    state = _build(
        OhdsiPromptRegistryConfig(
            packs_root=str(tmp_path),
            include_bundled=False,
            include_installed=False,
        )
    )
    server = GroundworkersMCPServer("test")

    @server.prompt("normalize_clinical_term")
    def core_prompt() -> str:
        return "core"

    plugin.register(server, state)

    assert server.call_prompt("normalize_clinical_term") == "core"
    report = plugin.verify_readiness(state).as_dict()
    collision = next(
        field
        for field in report["fields"]
        if field["key"].startswith("prompt_collision_")
    )
    assert collision["value"] == "colliding-pack"
    assert "existing server prompt" in collision["detail"]


def test_prompt_is_published_over_the_mcp_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mcp.server.fastmcp import FastMCP
    from mcp.shared.memory import create_connected_server_and_client_session

    state = _build(OhdsiPromptRegistryConfig())
    server = GroundworkersMCPServer("test")
    plugin.register(server, state)
    captured: dict[str, FastMCP] = {}

    def capture_run(app: FastMCP, transport: str) -> None:
        del transport
        captured["app"] = app

    monkeypatch.setattr(FastMCP, "run", capture_run)
    server.run(transport="stdio")

    async def exercise_protocol() -> None:
        async with create_connected_server_and_client_session(
            captured["app"]
        ) as session:
            listed = await session.list_prompts()
            published = next(
                prompt
                for prompt in listed.prompts
                if prompt.name == "rqt_structure_question"
            )
            assert published.title == "Structure an OHDSI research question"
            assert published.arguments is not None
            assert [argument.name for argument in published.arguments] == ["question"]
            result = await session.get_prompt(
                "rqt_structure_question",
                arguments={"question": "Does treatment work?"},
            )
            assert len(result.messages) == 1
            assert result.messages[0].role == "user"
            assert result.messages[0].content.type == "text"
            assert "Does treatment work?" in result.messages[0].content.text

    asyncio.run(exercise_protocol())


def test_tool_readiness_is_independent_of_plugin_registration_order() -> None:
    state = _build(OhdsiPromptRegistryConfig())
    server = GroundworkersMCPServer("test")
    plugin.register(server, state)

    initial = server.call("ohdsi_prompt_registry_status")
    initial_tools = next(
        field for field in initial["fields"] if field["key"] == "required_tools"
    )
    assert initial_tools["state"] == "warning"

    @server.tool("comparator_recommender_find_target")
    def find_target() -> None:
        pass

    @server.tool("comparator_recommender_recommend")
    def recommend() -> None:
        pass

    resolved = server.call("ohdsi_prompt_registry_status")
    resolved_tools = next(
        field for field in resolved["fields"] if field["key"] == "required_tools"
    )
    assert resolved_tools["state"] == "ready"
    assert resolved_tools["value"] == "None"


def test_readiness_matrix(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OA_CONFIG_PATH", raising=False)

    active = _build(OhdsiPromptRegistryConfig())
    active.available_tools = lambda: {
        "comparator_recommender_find_target",
        "comparator_recommender_recommend",
    }
    active_report = plugin.verify_readiness(active)
    assert active_report.state.value == "ready"
    active_packs = next(
        field for field in active_report.fields if field.key == "active_packs"
    )
    assert active_packs.detail == (
        "Each validated pack is listed in its own row below."
    )
    bundled_packs = next(
        field for field in active_report.fields if field.key == "source_bundled"
    )
    assert bundled_packs.detail == (
        "OHDSI research question templates (ohdsi-question-templates)"
    )
    pack = next(
        field
        for field in active_report.fields
        if field.key == "pack_ohdsi-question-templates"
    )
    assert pack.label == "Pack: OHDSI research question templates"
    assert pack.value == "bundled"
    assert pack.detail is not None
    assert "Documents: instructions, catalogue." in pack.detail
    assert "Schemas: study_intent." in pack.detail
    assert "Renderers: study_intent." in pack.detail

    standalone = _build(OhdsiPromptRegistryConfig())
    standalone_report = plugin.verify_readiness(standalone).as_dict()
    standalone_tools = next(
        field
        for field in standalone_report["fields"]
        if field["key"] == "required_tools"
    )
    assert standalone_tools["state"] == "ready"
    assert standalone_tools["value"] == "Not evaluated (no live server)"
    assert standalone_report["state"] == "ready"

    unmet = _build(OhdsiPromptRegistryConfig())
    unmet.available_tools = set
    unmet_report = plugin.verify_readiness(unmet).as_dict()
    required_tools = next(
        field for field in unmet_report["fields"] if field["key"] == "required_tools"
    )
    assert required_tools["state"] == "warning"
    assert "comparator_recommender_recommend" in required_tools["value"]

    empty = _build(
        OhdsiPromptRegistryConfig(
            packs_root=str(tmp_path), include_bundled=False, include_installed=False
        )
    )
    empty_report = plugin.verify_readiness(empty)
    assert empty_report.state.value == "warning"
    assert empty_report.fields[0].value == "0"
    assert empty_report.fields[0].detail == "No prompt packs are currently active."
    source_fields = {
        field.key: field for field in empty_report.fields if field.key.startswith("source_")
    }
    assert all(
        field.detail == "No active packs were loaded from this source."
        for field in source_fields.values()
    )

    absent = _build(
        OhdsiPromptRegistryConfig(
            packs_root=str(tmp_path / "absent"),
            include_bundled=False,
            include_installed=False,
        )
    )
    assert "does not exist" in json.dumps(plugin.verify_readiness(absent).as_dict())

    unanchored = _build(OhdsiPromptRegistryConfig(packs_root="relative"))
    assert "cannot be anchored" in json.dumps(
        plugin.verify_readiness(unanchored).as_dict()
    )

    rejected = _build(
        OhdsiPromptRegistryConfig(
            packs_root=str(Path(__file__).parent / "packs"),
            include_bundled=False,
            include_installed=False,
        )
    )
    report = plugin.verify_readiness(rejected).as_dict()
    assert len([field for field in report["fields"] if field["key"].startswith("rejection_")]) == 4


def test_generic_workflow_writes_registry_configuration(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    stack = StackConfig(
        connections={
            "cdm_main": ConnectionConfig(dialect="sqlite", database_name=":memory:")
        },
        databases={
            "cdm_db": CDMDatabaseConfig(
                connection="cdm_main", schema_name="main", vocab_schema="main"
            )
        },
    )
    save_stack_config(stack, path)
    service = PackageConfigMutationService(path, OhdsiPromptRegistryConfig)
    workflow = service.workflow(MutationOperation.UPDATE)
    controller = ConfigWizardController(workflow, service)

    snapshot = controller.start()
    snapshot = controller.submit(
        {
            "packs_root": "./prompt-packs",
            "include_bundled": False,
            "include_installed": True,
            "tool_aliases_enabled": False,
        }
    ).snapshot
    assert isinstance(snapshot.step, ReviewStep)
    assert snapshot.can_apply
    assert controller.apply().applied

    saved = load_stack_config_from_path(path)
    assert saved.tools["ohdsi_prompt_registry"] == {
        "packs_root": "./prompt-packs",
        "include_bundled": False,
        "include_installed": True,
        "tool_aliases_enabled": False,
    }
    assert OhdsiPromptRegistryConfig.validate_candidate(saved).packs_root == (
        "./prompt-packs"
    )

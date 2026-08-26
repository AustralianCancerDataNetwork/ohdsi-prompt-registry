from __future__ import annotations

import json
from pathlib import Path

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

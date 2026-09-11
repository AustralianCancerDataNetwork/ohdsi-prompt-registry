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
    # `packs_root` is not among them: the host's generic workflow builds no
    # field for an optional list, and silently omits it -- as it already does
    # for `enabled_packs`. Editing anything else must not disturb it.
    assert [field.key for field in snapshot.step.fields] == [
        "include_bundled",
        "include_installed",
        "tool_aliases_enabled",
    ]
    snapshot = controller.submit(
        {
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
        "include_bundled": False,
        "include_installed": True,
        "tool_aliases_enabled": False,
    }


def test_an_existing_packs_root_survives_an_unrelated_console_edit(
    tmp_path: Path,
) -> None:
    """The console cannot set the field, so it must not be able to lose it.

    An optional list has no field in the generic workflow, which would be a
    nuisance; silently dropping a configured value while an operator edited
    something else would be a fault.
    """

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
        tools={
            "ohdsi_prompt_registry": {
                "packs_root": ["/shared/packs", "/home/analyst/packs"],
                "include_bundled": True,
            }
        },
    )
    save_stack_config(stack, path)
    service = PackageConfigMutationService(path, OhdsiPromptRegistryConfig)
    controller = ConfigWizardController(
        service.workflow(MutationOperation.UPDATE), service
    )

    controller.start()
    controller.submit(
        {
            "include_bundled": False,
            "include_installed": True,
            "tool_aliases_enabled": False,
        }
    )
    assert controller.apply().applied

    saved = load_stack_config_from_path(path)
    assert saved.tools["ohdsi_prompt_registry"]["packs_root"] == [
        "/shared/packs",
        "/home/analyst/packs",
    ]


# ---- several filesystem roots -------------------------------------------


def _copy_valid_pack(destination: Path, *, title: str | None = None) -> Path:
    """Put a copy of the reference pack somewhere, optionally retitled.

    Retitling is how a test tells two copies of the same pack apart: they must
    share a name to collide at all, so the name cannot be the thing that
    identifies the winner.
    """

    import shutil

    source = Path(__file__).parent / "packs" / "valid-pack"
    target = destination / "valid-pack"
    shutil.copytree(source, target)
    if title is not None:
        manifest_path = target / "manifest.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        manifest["title"] = title
        manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return destination


def test_a_single_root_written_as_a_string_still_works(tmp_path: Path) -> None:
    """Configuration files in the wild spell this as a string, and a release
    should not require rewriting them."""

    _copy_valid_pack(tmp_path)

    config = OhdsiPromptRegistryConfig(
        packs_root=str(tmp_path), include_bundled=False, include_installed=False
    )

    assert config.packs_root == [str(tmp_path)]
    state = _build(config)
    assert [pack.manifest.name for pack in state.catalogue.all()] == ["valid-pack"]
    assert state.catalogue.all()[0].source == "filesystem"


def test_a_later_root_shadows_an_earlier_one_and_the_diagnostic_names_both(
    tmp_path: Path,
) -> None:
    """Precedence is declared order, so the last root is the one an operator
    adds to override what they already have."""

    shared = _copy_valid_pack(tmp_path / "shared", title="Shared copy")
    working = _copy_valid_pack(tmp_path / "working", title="Working copy")

    state = _build(
        OhdsiPromptRegistryConfig(
            packs_root=[str(shared), str(working)],
            include_bundled=False,
            include_installed=False,
        )
    )

    (active,) = state.catalogue.all()
    assert active.manifest.title == "Working copy"
    (shadow,) = state.catalogue.shadows
    assert shadow.pack == "valid-pack"
    assert shadow.winner == f"filesystem:{working}"
    assert shadow.loser == f"filesystem:{shared}"
    assert shadow.winner != shadow.loser


def test_one_unusable_root_does_not_silence_the_others(tmp_path: Path) -> None:
    _copy_valid_pack(tmp_path)

    state = _build(
        OhdsiPromptRegistryConfig(
            packs_root=[str(tmp_path), "relative"],
            include_bundled=False,
            include_installed=False,
        )
    )

    assert [pack.manifest.name for pack in state.catalogue.all()] == ["valid-pack"]
    report = plugin.verify_readiness(state)
    rows = {field.key: field for field in report.fields}
    assert rows["packs_root_1"].state.value == "ready"
    assert rows["packs_root_2"].state.value == "warning"
    assert "cannot be anchored" in (rows["packs_root_2"].detail or "")


def test_each_root_gets_its_own_readiness_row_naming_what_was_configured(
    tmp_path: Path,
) -> None:
    first = _copy_valid_pack(tmp_path / "first")
    second = tmp_path / "empty"
    second.mkdir()

    state = _build(
        OhdsiPromptRegistryConfig(
            packs_root=[str(first), str(second)],
            include_bundled=False,
            include_installed=False,
        )
    )

    rows = {field.key: field for field in plugin.verify_readiness(state).fields}
    assert rows["packs_root_1"].value == str(first)
    assert rows["packs_root_2"].value == str(second)
    assert "no active packs" in (rows["packs_root_2"].detail or "")


def test_a_single_root_keeps_the_readiness_key_it_has_always_had(
    tmp_path: Path,
) -> None:
    """An operator reading the setup console, and anything reading this report,
    should see no change from the field becoming a list."""

    _copy_valid_pack(tmp_path)

    state = _build(
        OhdsiPromptRegistryConfig(
            packs_root=[str(tmp_path)], include_bundled=False, include_installed=False
        )
    )

    keys = {field.key for field in plugin.verify_readiness(state).fields}
    assert "packs_root" in keys
    assert "packs_root_1" not in keys

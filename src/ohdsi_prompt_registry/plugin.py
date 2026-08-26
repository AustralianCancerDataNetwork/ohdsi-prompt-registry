"""Groundworkers composition root for the OHDSI Prompt Registry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from groundworkers.plugins import (
    PluginContext,
    PluginReadinessField,
    PluginReadinessResult,
    PluginReadinessState,
)
from oa_configurator import PackageConfigBase

from ohdsi_prompt_registry.catalogue import LoadedPack, PromptPackCatalogue
from ohdsi_prompt_registry.config import OhdsiPromptRegistryConfig
from ohdsi_prompt_registry.paths import resolve_packs_root
from ohdsi_prompt_registry.prompts import PromptRegistrationSkip, register_prompts
from ohdsi_prompt_registry.service import PromptRegistryService
from ohdsi_prompt_registry.sources import (
    BundledSource,
    FilesystemSource,
    InstalledSource,
)
from ohdsi_prompt_registry.tools import register_resources, register_tools


@dataclass
class OhdsiPromptRegistryState:
    """Objects and safe diagnostics shared by registration and readiness."""

    config: OhdsiPromptRegistryConfig
    catalogue: PromptPackCatalogue
    service: PromptRegistryService
    configured_root: str | None
    resolved_root: Path | None
    root_issue: str | None = None
    available_tools: Callable[[], set[str]] | None = field(default=None, repr=False)
    prompt_skips: tuple[PromptRegistrationSkip, ...] = ()


class OhdsiPromptRegistryPlugin:
    """Discover prompt packs and publish their validated content."""

    name = "ohdsi_prompt_registry"
    config_cls: ClassVar[type[PackageConfigBase] | None] = OhdsiPromptRegistryConfig

    def build(
        self,
        context: PluginContext,
        config: PackageConfigBase | None,
    ) -> OhdsiPromptRegistryState | None:
        """Build a visible registry state even when no packs are active."""

        del context
        if not isinstance(config, OhdsiPromptRegistryConfig):
            return None

        root: Path | None = None
        root_issue: str | None = None
        try:
            root = resolve_packs_root(config.packs_root)
        except ValueError as exc:
            root_issue = str(exc)

        sources = []
        if config.include_bundled:
            sources.append(BundledSource())
        if config.include_installed:
            sources.append(InstalledSource())
        if root is not None:
            sources.append(FilesystemSource(root))
        catalogue = PromptPackCatalogue(sources, enabled_packs=config.enabled_packs)
        return OhdsiPromptRegistryState(
            config=config,
            catalogue=catalogue,
            service=PromptRegistryService(catalogue),
            configured_root=config.packs_root,
            resolved_root=root,
            root_issue=root_issue,
        )

    def register(self, server: Any, state: object) -> None:
        """Register concrete resources and resource-reach tools."""

        resolved = self._state(state)
        resolved.available_tools = lambda: set(server.list_tools())
        register_resources(server, resolved.service)
        resolved.prompt_skips = register_prompts(server, resolved.service)
        register_tools(
            server,
            resolved.service,
            lambda: self.verify_readiness(resolved).as_dict(),
        )

    def verify_readiness(self, state: object) -> PluginReadinessResult:
        """Report active sources, safe rejections, shadows, and dependencies."""

        resolved = self._state(state)
        fields: list[PluginReadinessField] = []
        warnings = False
        active_packs = resolved.catalogue.all()
        active_count = len(active_packs)
        active_state = (
            PluginReadinessState.READY
            if active_count
            else PluginReadinessState.WARNING
        )
        warnings |= not active_count
        fields.append(
            PluginReadinessField(
                "active_packs",
                "Active packs",
                str(active_count),
                active_state,
                (
                    "Each validated pack is listed in its own row below."
                    if active_count
                    else "No prompt packs are currently active."
                ),
            )
        )

        counts = resolved.catalogue.source_counts()
        for source_kind in ("bundled", "installed", "filesystem"):
            source_packs = tuple(
                pack
                for pack in active_packs
                if _source_kind(pack.source) == source_kind
            )
            count = sum(
                count
                for label, count in counts.items()
                if label == source_kind or label.startswith(f"{source_kind}:")
            )
            fields.append(
                PluginReadinessField(
                    f"source_{source_kind}",
                    f"{source_kind.title()} packs",
                    str(count),
                    PluginReadinessState.READY,
                    _source_packs_detail(source_packs),
                )
            )

        for pack in active_packs:
            fields.append(
                PluginReadinessField(
                    f"pack_{pack.manifest.name}",
                    f"Pack: {pack.manifest.title}",
                    pack.source,
                    PluginReadinessState.READY,
                    _pack_detail(pack),
                )
            )

        if resolved.configured_root is None:
            fields.append(
                PluginReadinessField(
                    "packs_root",
                    "Filesystem root",
                    "Not configured",
                    PluginReadinessState.READY,
                )
            )
        elif resolved.root_issue is not None:
            warnings = True
            fields.append(
                PluginReadinessField(
                    "packs_root",
                    "Filesystem root",
                    resolved.configured_root,
                    PluginReadinessState.WARNING,
                    resolved.root_issue,
                )
            )
        elif resolved.resolved_root is None or not resolved.resolved_root.exists():
            warnings = True
            fields.append(
                PluginReadinessField(
                    "packs_root",
                    "Filesystem root",
                    resolved.configured_root,
                    PluginReadinessState.WARNING,
                    "The configured prompt-pack root does not exist.",
                )
            )
        else:
            filesystem_count = counts.get("filesystem", 0)
            root_state = (
                PluginReadinessState.READY
                if filesystem_count
                else PluginReadinessState.WARNING
            )
            warnings |= not filesystem_count
            fields.append(
                PluginReadinessField(
                    "packs_root",
                    "Filesystem root",
                    resolved.configured_root,
                    root_state,
                    None
                    if filesystem_count
                    else "The configured prompt-pack root contains no active packs.",
                )
            )

        for index, rejection in enumerate(resolved.catalogue.rejections, 1):
            warnings = True
            fields.append(
                PluginReadinessField(
                    f"rejection_{index}",
                    f"Rejected pack: {rejection.pack}",
                    rejection.source,
                    PluginReadinessState.WARNING,
                    rejection.reason,
                )
            )
        for index, shadow in enumerate(resolved.catalogue.shadows, 1):
            fields.append(
                PluginReadinessField(
                    f"shadow_{index}",
                    f"Shadowed pack: {shadow.pack}",
                    shadow.winner,
                    PluginReadinessState.READY,
                    f"Overrides {shadow.loser}.",
                )
            )

        for index, skip in enumerate(resolved.prompt_skips, 1):
            warnings = True
            fields.append(
                PluginReadinessField(
                    f"prompt_collision_{index}",
                    f"Skipped prompt: {skip.name}",
                    skip.losing_pack,
                    PluginReadinessState.WARNING,
                    f"Existing registration wins: {skip.existing_owner}.",
                )
            )

        required_tools = {
            tool
            for pack in resolved.catalogue.all()
            for tool in pack.manifest.requires_tools
        }
        if resolved.available_tools is None:
            fields.append(
                PluginReadinessField(
                    "required_tools",
                    "Advertised tool availability",
                    "Not evaluated (no live server)",
                    PluginReadinessState.READY,
                    (
                        "This standalone check has no running MCP server. Tool "
                        "availability is evaluated against the live server at runtime."
                    ),
                )
            )
        else:
            unmet = sorted(required_tools - resolved.available_tools())
            if unmet:
                warnings = True
            fields.append(
                PluginReadinessField(
                    "required_tools",
                    "Unmet advertised tools",
                    ", ".join(unmet) if unmet else "None",
                    (
                        PluginReadinessState.WARNING
                        if unmet
                        else PluginReadinessState.READY
                    ),
                    (
                        "Packs remain active; these tools are optional workflow dependencies."
                        if unmet
                        else None
                    ),
                )
            )

        readiness_state = (
            PluginReadinessState.WARNING if warnings else PluginReadinessState.READY
        )
        summary = (
            f"{active_count} prompt pack(s) active with warnings."
            if warnings
            else f"{active_count} prompt pack(s) active."
        )
        return PluginReadinessResult(readiness_state, summary, tuple(fields))

    @staticmethod
    def _state(state: object) -> OhdsiPromptRegistryState:
        if not isinstance(state, OhdsiPromptRegistryState):
            raise TypeError("OHDSI Prompt Registry received invalid plugin state.")
        return state


def _source_kind(source: str) -> str:
    """Return the stable source category from a safe catalogue label."""

    return source.partition(":")[0]


def _source_packs_detail(packs: tuple[LoadedPack, ...]) -> str:
    """List the active packs contributed by one configured source category."""

    if not packs:
        return "No active packs were loaded from this source."
    return "; ".join(
        f"{pack.manifest.title} ({pack.manifest.name})" for pack in packs
    )


def _pack_detail(pack: LoadedPack) -> str:
    """Summarize one validated pack and its published content."""

    manifest = pack.manifest
    content = [f"Documents: {', '.join(manifest.documents) or 'none'}. "]
    if manifest.schemas:
        content.append(f"Schemas: {', '.join(manifest.schemas)}. ")
    if manifest.prompts:
        content.append(f"Prompts: {', '.join(manifest.prompts)}. ")
    if manifest.render:
        content.append(f"Renderers: {', '.join(manifest.render)}. ")
    if manifest.requires_tools:
        content.append(f"Advertised tools: {', '.join(manifest.requires_tools)}. ")
    return (
        f"{manifest.name} v{manifest.version}. {manifest.scope_summary.strip()} "
        f"{''.join(content).strip()}"
    )


plugin = OhdsiPromptRegistryPlugin()

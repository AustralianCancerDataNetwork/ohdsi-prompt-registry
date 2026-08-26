from __future__ import annotations

from pathlib import Path

import yaml

from ohdsi_prompt_registry.catalogue import PromptPackCatalogue
from ohdsi_prompt_registry.sources import (
    BundledSource,
    FilesystemSource,
    InstalledSource,
)


def _write_pack(root: Path, name: str, title: str) -> Path:
    pack = root / name
    pack.mkdir(parents=True)
    (pack / "instructions.md").write_text(f"# {title}\n", encoding="utf-8")
    (pack / "manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "name": name,
                "title": title,
                "version": "1.0",
                "shareability": "public",
                "scope_summary": title,
                "documents": {
                    "instructions": {
                        "path": "instructions.md",
                        "mime_type": "text/markdown",
                        "description": title,
                    }
                },
                "schemas": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return pack


class _FakeEntryPoint:
    name = "fixture-distribution"

    def __init__(self, root: Path) -> None:
        self.root = root

    def load(self) -> Path:
        return self.root


class _BrokenEntryPoint:
    name = "broken-distribution"

    def load(self) -> Path:
        raise RuntimeError("fixture entry point failed")


def test_broken_packs_are_isolated_and_distinguishable() -> None:
    root = Path(__file__).parent / "packs"
    catalogue = PromptPackCatalogue([FilesystemSource(root)])

    assert [pack.manifest.name for pack in catalogue.all()] == ["valid-pack"]
    reasons = {rejection.pack: rejection.reason for rejection in catalogue.rejections}
    assert "does not match directory" in reasons["name-mismatch"]
    assert "is missing" in reasons["missing-file"]
    assert "not valid YAML" in reasons["bad-yaml"]
    assert "documants" in reasons["unknown-key"]


def test_precedence_across_all_sources_and_shadow_reporting(tmp_path: Path) -> None:
    bundled_root = tmp_path / "bundled"
    installed_root = tmp_path / "installed"
    filesystem_root = tmp_path / "filesystem"
    _write_pack(bundled_root, "shared-pack", "Bundled")
    _write_pack(installed_root, "shared-pack", "Installed")
    _write_pack(filesystem_root, "shared-pack", "Filesystem")

    installed = InstalledSource(
        provider=lambda **_kwargs: [_FakeEntryPoint(installed_root)]  # type: ignore[arg-type]
    )
    catalogue = PromptPackCatalogue(
        [BundledSource(bundled_root), installed, FilesystemSource(filesystem_root)]
    )

    active = catalogue.require("shared-pack")
    assert active.manifest.title == "Filesystem"
    assert active.source == "filesystem"
    assert [(shadow.winner, shadow.loser) for shadow in catalogue.shadows] == [
        ("installed:fixture-distribution", "bundled"),
        ("filesystem", "installed:fixture-distribution"),
    ]


def test_enabled_pack_allow_list_applies_before_loading(tmp_path: Path) -> None:
    _write_pack(tmp_path, "one", "One")
    _write_pack(tmp_path, "two", "Two")
    catalogue = PromptPackCatalogue(
        [FilesystemSource(tmp_path)], enabled_packs=["two"]
    )
    assert [pack.manifest.name for pack in catalogue.all()] == ["two"]


def test_bad_installed_entry_point_is_skipped(caplog) -> None:
    source = InstalledSource(
        provider=lambda **_kwargs: [_BrokenEntryPoint()]  # type: ignore[arg-type]
    )
    catalogue = PromptPackCatalogue([source])

    assert catalogue.all() == ()
    assert "broken-distribution" in caplog.text

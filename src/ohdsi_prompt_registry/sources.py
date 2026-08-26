"""Discovery sources for bundled, installed, and operator-authored packs."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from importlib import resources
from importlib.metadata import EntryPoint, entry_points
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Protocol, cast

logger = logging.getLogger(__name__)

PackCandidate = tuple[str, Traversable, str]


class PackSource(Protocol):
    """A source yields pack directory name, directory handle, and safe label."""

    def iter_packs(self) -> Iterator[PackCandidate]: ...


def _pack_directories(root: Traversable, source_label: str) -> Iterator[PackCandidate]:
    """Yield direct children containing a manifest in deterministic order."""

    try:
        children = sorted(root.iterdir(), key=lambda child: child.name)
    except (FileNotFoundError, NotADirectoryError, OSError):
        return
    for child in children:
        try:
            if child.is_dir() and child.joinpath("manifest.yaml").is_file():
                yield child.name, child, source_label
        except OSError:
            logger.warning("Could not inspect prompt pack %s; skipping it.", child.name)


@dataclass(frozen=True)
class BundledSource:
    """Packs distributed inside :mod:`ohdsi_prompt_registry.packs`."""

    root: Traversable | None = None
    source_label: str = "bundled"

    def iter_packs(self) -> Iterator[PackCandidate]:
        root = self.root or resources.files("ohdsi_prompt_registry.packs")
        yield from _pack_directories(root, self.source_label)


def _loaded_root(value: object) -> Traversable:
    """Turn an entry-point target into its package-data root."""

    if isinstance(value, (str, Path)):
        return Path(value)
    package_name = getattr(value, "__package__", None) or getattr(value, "__name__", None)
    if package_name:
        return resources.files(package_name)
    if all(hasattr(value, attr) for attr in ("iterdir", "joinpath", "is_dir")):
        return cast(Traversable, value)
    raise TypeError("entry point did not resolve to a package or traversable root")


@dataclass(frozen=True)
class InstalledSource:
    """Packs contributed through the dedicated package entry-point group."""

    group: str = "ohdsi_prompt_registry.packs"
    provider: Callable[..., Sequence[EntryPoint]] = entry_points

    def iter_packs(self) -> Iterator[PackCandidate]:
        for entry_point in self.provider(group=self.group):
            source_label = f"installed:{entry_point.name}"
            try:
                root = _loaded_root(entry_point.load())
                yield from _pack_directories(root, source_label)
            except Exception:
                logger.exception(
                    "Could not load prompt-pack entry point %s; skipping it.",
                    entry_point.name,
                )


@dataclass(frozen=True)
class FilesystemSource:
    """Packs underneath one configured local directory."""

    root: Path
    source_label: str = "filesystem"

    def iter_packs(self) -> Iterator[PackCandidate]:
        yield from _pack_directories(self.root, self.source_label)

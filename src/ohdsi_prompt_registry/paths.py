"""Resolve local pack roots without depending on the process working directory."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: The source label a single configured root carries, unchanged from when only
#: one was allowed. Kept so that a deployment with one root sees exactly the
#: diagnostics it saw before.
FILESYSTEM_LABEL = "filesystem"


@dataclass(frozen=True)
class ResolvedRoot:
    """One configured local root, resolved or refused on its own terms.

    A root that cannot be anchored is carried here rather than raised, because
    one bad entry in a list must not silence the others: an operator who adds a
    working copy alongside a shared directory should lose the working copy, not
    every pack they had.
    """

    configured: str
    label: str
    path: Path | None = None
    issue: str | None = None

    @property
    def usable(self) -> bool:
        return self.path is not None


def resolve_packs_root(
    value: str | None,
    *,
    environ: dict[str, str] | None = None,
) -> Path | None:
    """Resolve one ``packs_root`` value using the config-relative contract.

    Absolute paths and ``~`` are accepted directly. Relative values are anchored
    to the file named by ``OA_CONFIG_PATH``. A relative value with no absolute
    configuration-file anchor is refused instead of being interpreted against an
    arbitrary MCP server working directory.
    """

    if value is None:
        return None
    root = Path(value).expanduser()
    if root.is_absolute():
        return root

    environment = os.environ if environ is None else environ
    configured_path = environment.get("OA_CONFIG_PATH")
    if not configured_path:
        raise ValueError(
            "relative packs_root cannot be anchored because OA_CONFIG_PATH is unset"
        )
    config_path = Path(configured_path).expanduser()
    if not config_path.is_absolute():
        raise ValueError(
            "relative packs_root cannot be anchored because OA_CONFIG_PATH is relative"
        )
    return config_path.parent / root


def resolve_packs_roots(
    values: list[str] | None,
    *,
    environ: dict[str, str] | None = None,
) -> list[ResolvedRoot]:
    """Resolve every configured root, keeping each one's own outcome.

    Order is preserved and is precedence: later roots shadow earlier ones, the
    same way installed packs shadow bundled ones. That makes the last-declared
    root the one an operator edits to override what is already installed.

    Labels distinguish roots only when there is more than one, so a deployment
    with a single root keeps the plain ``filesystem`` label it has always had
    and nothing reading that label has to change.
    """

    if not values:
        return []
    distinguish = len(values) > 1
    resolved: list[ResolvedRoot] = []
    for configured in values:
        # The configured string, not the path it resolves to: the operator
        # wrote it, so echoing it back tells them nothing they did not already
        # know, while an expanded absolute path could describe the filesystem.
        label = f"{FILESYSTEM_LABEL}:{configured}" if distinguish else FILESYSTEM_LABEL
        try:
            resolved.append(
                ResolvedRoot(
                    configured=configured,
                    label=label,
                    path=resolve_packs_root(configured, environ=environ),
                )
            )
        except ValueError as exc:
            resolved.append(
                ResolvedRoot(configured=configured, label=label, issue=str(exc))
            )
    return resolved


__all__ = [
    "FILESYSTEM_LABEL",
    "ResolvedRoot",
    "resolve_packs_root",
    "resolve_packs_roots",
]

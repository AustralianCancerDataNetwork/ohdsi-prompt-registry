"""Resolve local pack roots without depending on the process working directory."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_packs_root(
    value: str | None,
    *,
    environ: dict[str, str] | None = None,
) -> Path | None:
    """Resolve ``packs_root`` using the interim config-relative contract.

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

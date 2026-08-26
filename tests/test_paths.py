from pathlib import Path

import pytest

from ohdsi_prompt_registry.paths import resolve_packs_root


def test_unset_root_stays_unset() -> None:
    assert resolve_packs_root(None, environ={}) is None


def test_absolute_and_home_paths_do_not_need_a_config_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert resolve_packs_root(str(tmp_path), environ={}) == tmp_path
    monkeypatch.setenv("HOME", str(tmp_path))
    assert resolve_packs_root("~/packs", environ={}) == tmp_path / "packs"


def test_relative_root_anchors_to_the_configuration_file(tmp_path: Path) -> None:
    assert resolve_packs_root(
        "prompt-packs", environ={"OA_CONFIG_PATH": str(tmp_path / "config.toml")}
    ) == tmp_path / "prompt-packs"


@pytest.mark.parametrize("environment", [{}, {"OA_CONFIG_PATH": "config.toml"}])
def test_unanchorable_relative_root_is_refused(environment: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="cannot be anchored"):
        resolve_packs_root("prompt-packs", environ=environment)

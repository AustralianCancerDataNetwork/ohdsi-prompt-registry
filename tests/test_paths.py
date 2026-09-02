from pathlib import Path

import pytest

from ohdsi_prompt_registry.paths import (
    FILESYSTEM_LABEL,
    resolve_packs_root,
    resolve_packs_roots,
)


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


# ---- several roots ------------------------------------------------------


def test_no_roots_configured_resolves_to_nothing() -> None:
    assert resolve_packs_roots(None, environ={}) == []
    assert resolve_packs_roots([], environ={}) == []


def test_one_root_keeps_the_plain_filesystem_label(tmp_path: Path) -> None:
    """A deployment with a single root must see exactly what it saw before the
    field became a list -- including in diagnostics, which quote the label."""

    resolved = resolve_packs_roots([str(tmp_path)], environ={})

    assert [(root.path, root.label) for root in resolved] == [
        (tmp_path, FILESYSTEM_LABEL)
    ]


def test_several_roots_are_labelled_distinguishably(tmp_path: Path) -> None:
    """Two roots both labelled 'filesystem' would make a shadow diagnostic read
    'filesystem overrides filesystem', which says nothing."""

    first, second = tmp_path / "a", tmp_path / "b"

    resolved = resolve_packs_roots([str(first), str(second)], environ={})

    labels = [root.label for root in resolved]
    assert labels == [f"filesystem:{first}", f"filesystem:{second}"]
    assert len(set(labels)) == 2


def test_declared_order_is_preserved_because_it_is_precedence(tmp_path: Path) -> None:
    order = [str(tmp_path / name) for name in ("a", "b", "c")]

    assert [root.configured for root in resolve_packs_roots(order, environ={})] == order


def test_one_unanchorable_root_does_not_cost_the_others(tmp_path: Path) -> None:
    """The whole point of resolving each root separately: an operator who adds a
    bad entry should lose that entry, not every pack they had."""

    resolved = resolve_packs_roots([str(tmp_path), "relative"], environ={})

    assert resolved[0].usable and resolved[0].path == tmp_path
    assert not resolved[1].usable
    assert "cannot be anchored" in (resolved[1].issue or "")


def test_a_refused_root_still_reports_what_was_configured(tmp_path: Path) -> None:
    """Its row in the readiness report has to name something an operator wrote."""

    (refused,) = resolve_packs_roots(["relative"], environ={})

    assert refused.configured == "relative"
    assert refused.path is None

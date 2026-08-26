from ohdsi_prompt_registry.catalogue import PromptPackCatalogue
from ohdsi_prompt_registry.sources import BundledSource


def test_reference_pack_loads_without_diagnostics() -> None:
    catalogue = PromptPackCatalogue([BundledSource()])

    assert [pack.manifest.name for pack in catalogue.all()] == [
        "ohdsi-question-templates"
    ]
    assert catalogue.rejections == []
    assert catalogue.shadows == []

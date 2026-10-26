"""The registry against the real installed data: every state and UT resolves, and no layer is claimed without a store."""

import pytest

from connectors.regions import data_root

pytestmark = pytest.mark.skipif(not (data_root() / "india" / "india_states.geojson").exists(),
                                reason="India boundary data is not installed")


def test_all_36_regions_resolve_and_layers_are_never_claimed_without_data() -> None:
    import dataset_registry

    registry = dataset_registry.build()
    assert len(registry["regions"]) == 36
    assert sum(r["type"] == "union_territory" for r in registry["regions"]) == 8
    for region in registry["regions"]:
        layers = region["layers"]
        assert layers["region_resolution"]["status"] == "verified", region["iso"]
        assert layers["place_search"]["status"] == "installed", region["iso"]
        for name in ("roads", "schools_hospitals_transport", "water_features", "public_facilities"):
            assert layers[name]["status"] in ("installed", "not_installed"), (region["iso"], name)
            assert layers[name]["status"] == "not_installed" or layers[name].get("store"), (region["iso"], name)
        assert layers["bhuvan"]["status"] == "not_integrated"

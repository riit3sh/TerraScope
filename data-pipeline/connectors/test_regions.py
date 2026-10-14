"""India coverage, state attribution across borders, and regional data selection."""

from __future__ import annotations

import json

import pytest
import shapely
from shapely.geometry import box, mapping

from connectors import regions
from connectors.local_osm import create_store
from connectors.regions import IndiaCoverage, LocalDataMissing


def _parcel(lon: float, lat: float, dlon: float = 0.001, dlat: float = 0.001) -> dict:
    return {"type": "Polygon", "coordinates": [[
        [lon, lat], [lon + dlon, lat], [lon + dlon, lat + dlat], [lon, lat + dlat], [lon, lat],
    ]]}


# Two adjacent "states" meeting at lon 79.0, the second with an enclave of a third.
STATE_A = box(78.0, 10.0, 79.0, 12.0)
STATE_B = box(79.0, 10.0, 80.0, 12.0).difference(box(79.4, 11.0, 79.6, 11.2))
ENCLAVE = box(79.4, 11.0, 79.6, 11.2)


@pytest.fixture()
def root(tmp_path):
    india_dir = tmp_path / regions.INDIA_DIR
    india_dir.mkdir()
    features = [
        {"type": "Feature", "properties": {"shapeName": name, "shapeISO": iso}, "geometry": mapping(geometry)}
        for name, iso, geometry in (("State A", "IN-AA", STATE_A), ("State B", "IN-BB", STATE_B), ("Enclave", "IN-EN", ENCLAVE))
    ]
    (india_dir / regions.STATES_FILE).write_text(json.dumps({"type": "FeatureCollection", "features": features}))
    (india_dir / regions.UNION_FILE).write_bytes(shapely.to_wkb(shapely.union_all([STATE_A, STATE_B, ENCLAVE])))
    (india_dir / regions.MANIFEST_NAME).write_text(json.dumps({"source": "test", "licence": "test"}))
    return tmp_path


def test_parcel_inside_one_state(root) -> None:
    result = IndiaCoverage.load(root).check(_parcel(78.5, 11.0))
    assert result["status"] == "inside"
    assert [s["name"] for s in result["states"]] == ["State A"]
    assert result["crosses_state_border"] is False


def test_parcel_crossing_a_state_border_lists_both_states(root) -> None:
    """Not silently assigned to the centroid's state."""
    result = IndiaCoverage.load(root).check(_parcel(78.999, 11.0, dlon=0.004))  # 25% in A, 75% in B
    assert result["status"] == "inside"
    shares = {s["name"]: s["share"] for s in result["states"]}
    assert shares["State B"] == pytest.approx(0.75, abs=0.01)
    assert shares["State A"] == pytest.approx(0.25, abs=0.01)
    assert result["crosses_state_border"] is True


def test_union_territory_enclave_is_accepted(root) -> None:
    result = IndiaCoverage.load(root).check(_parcel(79.5, 11.1))
    assert result["status"] == "inside"
    assert result["states"][0]["name"] == "Enclave"


def test_parcel_outside_india_is_rejected(root) -> None:
    result = IndiaCoverage.load(root).check(_parcel(85.3, 27.7))  # Kathmandu
    assert result["status"] == "outside_india"
    assert "outside India" in result["reason"]
    assert result["states"] == []


def test_parcel_mostly_across_the_national_boundary_is_rejected(root) -> None:
    result = IndiaCoverage.load(root).check(_parcel(79.999, 11.0, dlon=0.004))  # 25% inside
    assert result["status"] == "outside_india"
    assert result["inside_india_share"] == pytest.approx(0.25, abs=0.01)


def test_generalised_coastline_tolerance(root) -> None:
    """Under 1% outside the generalised boundary is accepted; more is not."""
    assert IndiaCoverage.load(root).check(_parcel(79.99905, 11.0, dlon=0.1))["status"] == "outside_india"
    tiny_overhang = _parcel(79.9, 11.0, dlon=0.1005)  # 0.5% beyond lon 80.0
    assert IndiaCoverage.load(root).check(tiny_overhang)["status"] == "inside"


def test_missing_boundary_is_a_setup_error_not_a_rejection(tmp_path) -> None:
    with pytest.raises(LocalDataMissing, match="fetch-data"):
        IndiaCoverage.load(tmp_path)


def _install_region(root, slug_name: str, geometry) -> None:
    directory = root / "regions" / slug_name
    directory.mkdir(parents=True)
    create_store(directory / regions.REGION_STORE).close()
    (directory / regions.REGION_BOUNDARY).write_text(json.dumps({"type": "Feature", "properties": {}, "geometry": mapping(geometry)}))
    (directory / regions.MANIFEST_NAME).write_text(json.dumps({"label": slug_name}))


def test_region_selection_uses_the_installed_cache_only_where_it_is_complete(root) -> None:
    _install_region(root, "state-a", STATE_A)
    regions._regions.clear()
    assert regions.region_for(_parcel(78.5, 11.0), root).slug == "state-a"
    # Valid Indian parcels without regional data: no region, not an error.
    assert regions.region_for(_parcel(79.5, 10.5), root) is None
    # A parcel straddling the region's edge is not fully covered by its store.
    assert regions.region_for(_parcel(78.999, 11.0, dlon=0.004), root) is None
    regions._regions.clear()


def test_slug_matches_fetch_data_region_names() -> None:
    assert regions.slug("Tamil Nādu") == "tamil-nadu"
    assert regions.slug("Dādra and Nagar Haveli and Damān and Diu") == "dadra-and-nagar-haveli-and-daman-and-diu"

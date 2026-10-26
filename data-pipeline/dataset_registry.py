"""Dataset registry: for each of India's 36 states and union territories, which data layer is actually usable.

    python dataset_registry.py        writes docs/datasets/registry.json and docs/DATASET_REGISTRY.md

Every status is tested, not assumed. A sample point inside each region (its representative point) is run through
the same code the analysis uses: region resolution, the local store it would read, and the layers that store holds.
"installed" means a local layer covers the region and answered a lookup; "remote" means the app reads a global
service at analysis time (not checked here per region); "not_installed" / "not_integrated" are unknowns, never
negative findings. A region can be selectable while a layer is unavailable; the registry says so per layer.
"""

from __future__ import annotations

import json
import math
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from connectors import public_land  # noqa: E402
from connectors.local_osm import LocalOSM  # noqa: E402
from connectors.regions import data_root, india_coverage, region_for  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
UT = {"IN-AN", "IN-CH", "IN-DH", "IN-DL", "IN-JK", "IN-LA", "IN-LD", "IN-PY"}
# Layers read from global services at analysis time; their coverage is global by construction (not tested here).
REMOTE = {
    "land_cover_2017_2023": ("Impact Observatory / Esri 10 m annual land cover (Microsoft Planetary Computer)", "10 m", "2017-2023", "CC BY 4.0"),
    "sentinel2": ("Sentinel-2 L2A (Microsoft Planetary Computer)", "10 m", "2015-present", "Copernicus open licence"),
    "river_flood": ("JRC river flood hazard maps v2.1.2", "~90 m", "modelled return periods", "CC BY 4.0"),
}


def _ascii(value: str | None) -> str:
    return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().casefold().strip()


def _square(lon: float, lat: float, size: float = 0.0005) -> dict:
    return {"type": "Polygon", "coordinates": [[[lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat + size], [lon, lat]]]}


def _dem_tile(root: Path, lon: float, lat: float) -> bool:
    name = f"Copernicus_DSM_COG_10_N{math.floor(lat):02d}_00_E{math.floor(lon):03d}_00_DEM.tif"
    return (root / "rasters" / "dem" / name).exists()


def _gsw_tile(root: Path, lon: float, lat: float) -> bool:
    name = f"occurrence_{math.floor(lon / 10) * 10}E_{math.floor(lat / 10) * 10 + 10}Nv1_4_2021.tif"
    return (root / "rasters" / "gsw" / name).exists()


def build(root: Path | None = None) -> dict:
    root = root or data_root()
    coverage = india_coverage()
    places = sqlite3.connect(f"file:{(root / 'places' / 'places.sqlite').as_posix()}?mode=ro", uri=True)
    place_states: dict[str, int] = {}
    for state, count in places.execute("SELECT state, COUNT(*) FROM places GROUP BY state"):
        place_states[_ascii(state)] = place_states.get(_ascii(state), 0) + count
    regions = []
    for state in sorted(coverage.states, key=lambda s: s["iso"]):
        point = state["geometry"].representative_point()
        lon, lat = round(point.x, 5), round(point.y, 5)
        polygon = _square(lon, lat)
        resolved = coverage.check(polygon)
        resolved_iso = [s["iso"] for s in resolved.get("states") or []]
        region = region_for(polygon)
        layers: dict[str, dict] = {
            "boundary": {"status": "installed", "source": "geoBoundaries gbOpen IND ADM1 (CC BY 2.5 IN), 2011 boundaries"},
            "region_resolution": {"status": "verified" if resolved_iso == [state["iso"]] else "failed",
                                  "detail": f"sample point {lat},{lon} resolved to {resolved_iso}"},
            "place_search": {"status": "installed" if place_states.get(_ascii(state["name"])) else "no_rows_found",
                             "detail": f"{place_states.get(_ascii(state['name']), 0):,} GeoNames rows"},
        }
        if region is None:
            for layer in ("roads", "schools_hospitals_transport", "water_features", "public_facilities"):
                layers[layer] = {"status": "not_installed", "detail": "no local store covers this region"}
        else:
            osm = LocalOSM(region.osm_store)
            try:
                as_of = (osm.meta.get("data_as_of") or "")[:10]
                for layer, probe in (("roads", "road"), ("schools_hospitals_transport", "school"), ("water_features", "water")):
                    if not osm.has_layer(probe):
                        layers[layer] = {"status": "not_installed", "store": region.slug,
                                         "detail": f"the {region.slug} store does not hold {probe}s"}
                        continue
                    hit = osm.nearest(lon, lat, probe, max_distance_m=50_000)
                    layers[layer] = {"status": "installed", "store": region.slug, "data_as_of": as_of,
                                     "detail": (f"nearest {probe} to the sample point: {hit['distance_m']:,.0f} m" if hit
                                                else f"no {probe} mapped within 50 km of the sample point (not proof of absence)")}
            finally:
                osm.close()
            store = region.path / public_land.STORE_NAME
            if store.exists():
                result = public_land.assess(polygon, store)
                layers["public_facilities"] = {"status": "installed", "store": region.slug, "data_as_of": result.get("data_as_of"),
                                               "detail": f"{len(result['nearby'])} facility categories within 2 km of the sample point"}
            else:
                layers["public_facilities"] = {"status": "not_installed", "detail": f"no public-facility store in {region.slug}"}
        layers["dem"] = {"status": "installed" if _dem_tile(root, lon, lat) else "remote",
                         "detail": "Copernicus GLO-30 tile on disk" if _dem_tile(root, lon, lat) else "read from Planetary Computer at analysis time"}
        layers["surface_water"] = {"status": "installed" if _gsw_tile(root, lon, lat) else "remote",
                                   "detail": "JRC GSW tile on disk" if _gsw_tile(root, lon, lat) else "read remotely at analysis time"}
        for key, (source, *_rest) in REMOTE.items():
            layers[key] = {"status": "remote", "detail": source}
        layers["land_records"] = {"status": "manual_guide" if state["iso"] == "IN-TN" else "not_integrated",
                                  "detail": "official portals listed; buyer records checks" if state["iso"] == "IN-TN" else "no state guide yet"}
        layers["bhuvan"] = {"status": "not_integrated",
                            "detail": "Bhuvan terms: viewing only; integration needs written authorization from DOS/ISRO/NRSC"}
        regions.append({"iso": state["iso"], "name": state["name"], "type": "union_territory" if state["iso"] in UT else "state",
                        "sample_point": [lat, lon], "layers": layers})
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "regions": regions,
            "remote_sources": {k: dict(zip(("source", "resolution", "period", "licence"), v)) for k, v in REMOTE.items()}}


SHORT = {"installed": "yes", "verified": "yes", "remote": "remote", "not_installed": "**no**", "not_integrated": "no",
         "manual_guide": "manual", "failed": "**FAILED**", "no_rows_found": "**none**"}


def markdown(registry: dict) -> str:
    cols = ("region_resolution", "place_search", "roads", "schools_hospitals_transport", "water_features",
            "public_facilities", "dem", "surface_water", "land_records", "bhuvan")
    head = ["Region", "Type", "Resolves", "Places", "Roads", "POIs", "Water", "Public fac.", "DEM", "GSW", "Land records", "Bhuvan"]
    lines = ["# Dataset registry: 28 states and 8 union territories", "",
             f"Generated {registry['generated_at']} by `data-pipeline/dataset_registry.py` from the data on disk.",
             "Each cell is tested at a sample point inside the region. **no** = not installed: unknown, never a negative finding.",
             "Land cover 2017-2023, Sentinel-2 and JRC river flood maps are read remotely for every region (global coverage).", "",
             "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in registry["regions"]:
        lines.append(f"| {r['name']} ({r['iso']}) | {'UT' if r['type'] == 'union_territory' else 'State'} | "
                     + " | ".join(SHORT.get(r["layers"][c]["status"], r["layers"][c]["status"]) for c in cols) + " |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    data = build()
    out = ROOT / "docs" / "datasets"
    out.mkdir(parents=True, exist_ok=True)
    (out / "registry.json").write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    (ROOT / "docs" / "DATASET_REGISTRY.md").write_text(markdown(data), encoding="utf-8")
    failed = [r["iso"] for r in data["regions"] if r["layers"]["region_resolution"]["status"] != "verified"]
    print(f"{len(data['regions'])} regions; resolution failures: {failed or 'none'}")

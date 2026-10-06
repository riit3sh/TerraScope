"""Install TerraScope's local data: the India coverage boundary and regional caches.

    python fetch_data.py                      India boundary only (~46 MB), lists regions
    python fetch_data.py tamil-nadu           build one region (any state/UT slug works)
    python fetch_data.py --list               show regions and what is installed

(run by: terrascope.cmd fetch-data [region])

Nothing India-wide is downloaded automatically. A region build downloads its
Geofabrik India zone extract (reusing one already on disk), builds a local
OpenStreetMap store clipped to the region plus 5 km, and caches the JRC Global
Surface Water and Copernicus DEM tiles for the region. Analyses work without a
region; the region adds local accessibility and water-feature evidence and lets
the rasters be read from disk instead of remotely.

Layout, under data-cache/ (git-ignored):
  india/          india_states.geojson, india_boundary.wkb, manifest.json
  regions/<slug>/ osm.sqlite, boundary.geojson, manifest.json
  rasters/        gsw/ and dem/ tiles, shared by every region
  downloads/      Geofabrik extracts and zone .poly files
  flood-hazard/   JRC river flood hazard tile index and cached parcel results
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from connectors.local_osm import create_store, write_features  # noqa: E402
from connectors.regions import (  # noqa: E402
    INDIA_DIR, MANIFEST_NAME, REGION_BOUNDARY, REGION_STORE, STATES_FILE, UNION_FILE, data_root, slug,
)


GEOBOUNDARIES_API = "https://www.geoboundaries.org/api/current/gbOpen/IND/ADM1/"
GEOFABRIK = "https://download.geofabrik.de/asia/india"
ZONES = ("central-zone", "eastern-zone", "north-eastern-zone", "northern-zone", "southern-zone", "western-zone")
GSW_BASE = "https://storage.googleapis.com/global-surface-water/downloads2021"
PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
PC_SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
CLIP_BUFFER_DEG = 0.05  # ~5 km: matches the nearest-feature search radius
# Regions that bundle enclaves with the state around them.
REGION_STATES = {"tamil-nadu": ["IN-TN", "IN-PY"]}
REGION_LABELS = {"tamil-nadu": "Tamil Nadu and Puducherry"}

USER_AGENT = "TerraScope/0.1 (local data build)"
NON_ROAD = {
    "footway", "path", "steps", "cycleway", "bridleway", "corridor", "pedestrian", "platform",
    "proposed", "construction", "raceway", "escape", "elevator", "service", "track", "bus_stop",
}
WATERWAYS = {"river", "canal", "drain", "stream", "ditch", "tidal_channel"}


def log(message: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {message}", flush=True)


def download(url: str, target: Path, session: requests.Session) -> Path:
    """Stream to a .part file and rename, so an interrupted run never leaves a truncated file."""
    if target.exists() and target.stat().st_size > 0:
        log(f"  have {target.name} ({target.stat().st_size / 1e6:.0f} MB)")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(target.suffix + ".part")
    for attempt in range(1, 5):
        try:
            with session.get(url, stream=True, timeout=(15, 120), headers={"User-Agent": USER_AGENT}) as response:
                response.raise_for_status()
                total = int(response.headers.get("Content-Length") or 0)
                done, last = 0, 0
                with open(part, "wb") as handle:
                    for chunk in response.iter_content(1 << 20):
                        handle.write(chunk)
                        done += len(chunk)
                        if done - last >= 100 << 20:
                            last = done
                            log(f"  {target.name}: {done / 1e6:.0f}/{total / 1e6:.0f} MB")
            if total and part.stat().st_size != total:
                raise requests.ConnectionError(f"got {part.stat().st_size} of {total} bytes")
            break
        except requests.RequestException as error:
            # Transient stalls on large downloads: start the file again, a few times.
            if attempt == 4:
                raise RuntimeError(f"{target.name}: download failed after {attempt} attempts: {error}") from error
            log(f"  {target.name}: attempt {attempt} failed ({error}); retrying")
            time.sleep(5 * attempt)
    part.replace(target)
    log(f"  downloaded {target.name} ({target.stat().st_size / 1e6:.0f} MB)")
    return target


def check_disk(directory: Path, need_bytes: int) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(directory).free
    log(f"Free disk at {directory}: {free / 1e9:.1f} GB (this step needs about {need_bytes / 1e9:.1f} GB)")
    if free < need_bytes + 2_000_000_000:
        raise SystemExit("Not enough free disk space (keeping 2 GB spare); nothing was downloaded or deleted.")


# --- migration of the first (Tamil Nadu-only) layout -------------------------------

def migrate_legacy(root: Path) -> None:
    """Move tn-data/ (2026-10-06 layout) into data-cache/ without deleting anything."""
    legacy = root.parent / "tn-data"
    if not legacy.exists():
        return
    log(f"Moving the earlier Tamil Nadu cache {legacy} into {root} ...")
    moves = [(legacy / "gsw", root / "rasters" / "gsw"), (legacy / "dem", root / "rasters" / "dem"),
             (legacy / "downloads", root / "downloads")]
    for source, target in moves:
        if source.exists():
            target.mkdir(parents=True, exist_ok=True)
            for item in source.iterdir():
                if not (target / item.name).exists():
                    item.replace(target / item.name)
    archive = root / "regions" / "tamil-nadu" / "previous-build-2026-10-06"
    archive.mkdir(parents=True, exist_ok=True)
    for name in ("tn_osm.sqlite", "tn_boundary.geojson", "manifest.json"):
        if (legacy / name).exists():
            (legacy / name).replace(archive / name)
    for directory in sorted(legacy.rglob("*"), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    if not any(legacy.iterdir()):
        legacy.rmdir()
    log("  moved; the previous store and manifest are kept under regions/tamil-nadu/previous-build-2026-10-06")


# --- India boundary --------------------------------------------------------------------

def install_india(root: Path, session: requests.Session) -> dict:
    directory = root / INDIA_DIR
    if (directory / STATES_FILE).exists() and (directory / UNION_FILE).exists():
        log(f"India boundary already installed ({directory})")
        return json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    import shapely

    check_disk(root, 200_000_000)
    meta = session.get(GEOBOUNDARIES_API, timeout=60).json()
    log(f"Downloading the India state/UT boundaries ({meta['boundarySource']}, {meta['boundaryLicense']}) ...")
    states_path = download(meta["gjDownloadURL"], directory / STATES_FILE, session)
    collection = json.loads(states_path.read_text(encoding="utf-8"))
    from shapely.geometry import shape

    log("Precomputing the India outline (union of 36 states/UTs) ...")
    india = shapely.union_all([shape(feature["geometry"]) for feature in collection["features"]])
    (directory / UNION_FILE).write_bytes(shapely.to_wkb(india))
    manifest = {
        "source": f"geoBoundaries gbOpen IND ADM1 ({meta['boundarySource']})",
        "source_url": meta["gjDownloadURL"],
        "licence": meta["boundaryLicense"],
        "boundary_year_represented": meta.get("boundaryYearRepresented"),
        "data_as_of": meta.get("sourceDataUpdateDate"),
        "build_date": meta.get("buildDate"),
        "units": len(collection["features"]),
        "limitations": (
            "Not a Survey of India boundary. Coastlines and borders are generalised; a parcel may extend up to "
            "1% of its area beyond them. Boundaries follow the source's depiction of India."
        ),
        "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "size_bytes": states_path.stat().st_size,
    }
    (directory / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"India boundary installed: {manifest['units']} states/UTs")
    return manifest


def load_states(root: Path) -> dict[str, dict]:
    from shapely.geometry import shape

    collection = json.loads((root / INDIA_DIR / STATES_FILE).read_text(encoding="utf-8"))
    return {
        feature["properties"]["shapeISO"]: {
            "name": feature["properties"]["shapeName"], "geometry": shape(feature["geometry"]),
        }
        for feature in collection["features"]
    }


def region_catalogue(root: Path) -> dict[str, list[str]]:
    """Every state/UT is a region; some regions bundle enclaves."""
    catalogue = {slug(state["name"]): [iso] for iso, state in load_states(root).items()}
    catalogue.update(REGION_STATES)
    return catalogue


# --- Geofabrik zone selection ---------------------------------------------------------

def _parse_poly(text: str):
    from shapely.geometry import MultiPolygon, Polygon

    outers, holes, current, inner = [], [], None, False
    for line in [line.strip() for line in text.splitlines()][1:]:
        if line == "END":
            if current is not None:
                (holes if inner else outers).append(Polygon(current))
                current = None
            continue
        if current is None:
            inner, current = line.startswith("!"), []
            continue
        x, y = map(float, line.split()[:2])
        current.append((x, y))
    shell = MultiPolygon(outers).buffer(0)
    return shell.difference(MultiPolygon(holes).buffer(0)) if holes else shell


def zone_for(region_geometry, root: Path, session: requests.Session) -> str:
    """The Geofabrik India zone extract that covers most of the region."""
    shares = {}
    for zone in ZONES:
        path = download(f"{GEOFABRIK}/{zone}.poly", root / "downloads" / f"{zone}.poly", session)
        polygon = _parse_poly(path.read_text(encoding="utf-8"))
        shares[zone] = region_geometry.intersection(polygon).area / region_geometry.area
    best = max(shares, key=shares.get)
    log(f"  Geofabrik zone: {best} covers {shares[best] * 100:.1f}% of the region")
    if shares[best] < 0.98:
        log("  NOTE: the OSM extract does not cover the whole region as drawn in the boundary file; "
            "parcels outside it will report accessibility as unavailable.")
    return best


# --- OpenStreetMap ---------------------------------------------------------------------

def _classify(obj, tags) -> list[tuple[str, str]]:
    """Which layers an OSM object belongs to, as (layer, class) pairs."""
    out: list[tuple[str, str]] = []
    is_area = obj.is_area()
    is_node = obj.is_node()
    is_way = obj.is_way()
    highway = tags.get("highway")
    if is_way and highway and highway not in NON_ROAD and tags.get("area") != "yes":
        out.append(("road", highway))
    if is_way and tags.get("waterway") in WATERWAYS:
        out.append(("waterway", tags["waterway"]))
    # Points of interest come from nodes and areas; the plain way behind an area is skipped.
    if is_node or is_area:
        amenity = tags.get("amenity")
        if amenity == "school":
            out.append(("school", "school"))
        if amenity == "hospital" or tags.get("healthcare") == "hospital":
            out.append(("hospital", "hospital"))
        if amenity == "bus_station":
            out.append(("bus", "bus_station"))
        if tags.get("railway") in ("station", "halt"):
            out.append(("rail_station", "subway" if tags.get("station") == "subway" else tags["railway"]))
    if is_node and highway == "bus_stop":
        out.append(("bus", "bus_stop"))
    if is_area:
        if tags.get("natural") == "water":
            out.append(("water", tags.get("water") or "water"))
        elif tags.get("landuse") == "reservoir":
            out.append(("water", "reservoir"))
        elif tags.get("waterway") == "riverbank":
            out.append(("water", "river"))
    return out


def build_osm(pbf: Path, coverage, directory: Path) -> dict:
    """Local store of the region's features within 5 km of its coverage polygon."""
    import osmium
    import shapely
    from shapely import wkb as shapely_wkb

    as_of = osmium.FileProcessor(str(pbf)).header.get("osmosis_replication_timestamp") or ""
    log(f"Building the local OSM store from {pbf.name} (data up to {as_of or 'unknown'}) ...")
    factory = osmium.geom.WKBFactory()
    directory.mkdir(parents=True, exist_ok=True)
    tmp = directory / (REGION_STORE + ".building")
    tmp.unlink(missing_ok=True)
    connection = create_store(tmp)
    clip = coverage.buffer(CLIP_BUFFER_DEG)
    shapely.prepare(clip)
    min_lon, min_lat, max_lon, max_lat = clip.bounds
    batch: list[tuple] = []
    counts: dict[str, int] = {}
    skipped = 0
    started = time.monotonic()

    processor = (
        osmium.FileProcessor(str(pbf))
        .with_locations()
        .with_areas(osmium.filter.KeyFilter("natural", "landuse", "amenity", "healthcare", "railway", "waterway"))
        .with_filter(osmium.filter.KeyFilter("highway", "amenity", "healthcare", "railway", "waterway", "natural", "landuse"))
    )
    for obj in processor:
        tags = obj.tags
        layers = _classify(obj, tags)
        if not layers:
            continue
        try:
            if obj.is_node():
                geometry_hex = factory.create_point(obj)
            elif obj.is_area():
                geometry_hex = factory.create_multipolygon(obj)
            else:
                geometry_hex = factory.create_linestring(obj)
            geometry = shapely_wkb.loads(geometry_hex, hex=True)
        except Exception:  # broken or incomplete OSM geometry
            skipped += 1
            continue
        x0, y0, x1, y1 = geometry.bounds
        if x1 < min_lon or x0 > max_lon or y1 < min_lat or y0 > max_lat:
            continue
        if obj.is_area():
            osm_id = f"{'w' if obj.from_way() else 'r'}{obj.orig_id()}"
        else:
            osm_id = f"{'n' if obj.is_node() else 'w'}{obj.id}"
        keep = {key: tags.get(key) for key in ("name", "name:en", "ref", "access", "surface", "water", "operator") if tags.get(key)}
        for layer, cls in layers:
            batch.append((layer, cls, tags.get("name:en") or tags.get("name") or tags.get("ref"), osm_id, keep, geometry))
            counts[layer] = counts.get(layer, 0) + 1
        if len(batch) >= 50_000:
            write_features(connection, batch)
            batch.clear()
            log(f"  {sum(counts.values()):,} features so far ({time.monotonic() - started:.0f}s)")
    write_features(connection, batch)
    connection.commit()

    log("Clipping features to the region + 5 km ...")
    removed = 0
    cursor = connection.execute("SELECT id, geom FROM features")
    while True:
        rows = cursor.fetchmany(100_000)
        if not rows:
            break
        geometries = shapely.from_wkb([row[1] for row in rows])
        outside = [(row[0],) for row, inside in zip(rows, shapely.intersects(clip, geometries)) if not inside]
        if outside:
            connection.executemany("DELETE FROM features WHERE id = ?", outside)
            connection.executemany("DELETE FROM features_rtree WHERE id = ?", outside)
            removed += len(outside)
    layer_counts = dict(connection.execute("SELECT layer, COUNT(*) FROM features GROUP BY layer").fetchall())
    meta = {
        "source": "OpenStreetMap, Geofabrik India zone extract",
        "source_url": f"{GEOFABRIK}/{pbf.name}",
        "licence": "ODbL 1.0 - (c) OpenStreetMap contributors",
        "data_as_of": as_of,
        "extract_file": pbf.name,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    connection.executemany("INSERT OR REPLACE INTO store_meta VALUES (?, ?)", list(meta.items()))
    connection.commit()
    connection.execute("VACUUM")
    connection.close()
    target = directory / REGION_STORE
    tmp.replace(target)
    log(f"OSM store: {layer_counts}; {removed:,} outside the clip removed; {skipped} broken geometries skipped; "
        f"{target.stat().st_size / 1e6:.0f} MB in {time.monotonic() - started:.0f}s")
    return {**meta, "layers": layer_counts, "size_bytes": target.stat().st_size}


# --- rasters -------------------------------------------------------------------------

def _sign(href: str, session: requests.Session, attempts: int = 6) -> str:
    """Planetary Computer SAS-signed URL. The endpoint rate-limits, so back off and retry."""
    for attempt in range(attempts):
        response = session.get(PC_SIGN, params={"href": href}, timeout=30)
        if response.ok:
            return response.json()["href"]
        wait = float(response.headers.get("Retry-After") or 5 * (attempt + 1))
        log(f"  signing returned HTTP {response.status_code}; retrying in {wait:.0f}s")
        time.sleep(wait)
    raise RuntimeError(f"Planetary Computer would not sign {href} (last HTTP {response.status_code})")


def fetch_rasters(coverage, root: Path, session: requests.Session) -> dict:
    """Tiles touched by each part of the region (not its overall bounding box, which for
    regions with distant enclaves would pull in a large empty area)."""
    import math

    parts = list(getattr(coverage, "geoms", [coverage]))
    gsw_cells, dem_cells = set(), set()
    for part in parts:
        west, south, east, north = part.bounds
        gsw_cells |= {(x, y) for x in range(math.floor(west / 10) * 10, math.floor(east / 10) * 10 + 1, 10)
                      for y in range(math.floor(south / 10) * 10, math.floor(north / 10) * 10 + 1, 10)}
        dem_cells |= {(x, y) for x in range(math.floor(west), math.floor(east) + 1)
                      for y in range(math.floor(south), math.floor(north) + 1)}
    gsw_files = []
    for x, y in sorted(gsw_cells):
        tile = f"{abs(x)}{'E' if x >= 0 else 'W'}_{abs(y + 10)}{'N' if y + 10 >= 0 else 'S'}"
        for layer in ("occurrence", "extent"):
            name = f"{layer}_{tile}v1_4_2021.tif"
            gsw_files.append(download(f"{GSW_BASE}/{layer}/{name}", root / "rasters" / "gsw" / name, session))
    # One catalogue search lists the DEM tiles that exist (open-sea cells have none).
    response = session.post(PC_STAC, json={"collections": ["cop-dem-glo-30"], "bbox": list(coverage.bounds), "limit": 1000}, timeout=60)
    response.raise_for_status()
    dem_files = []
    for item in response.json()["features"]:
        transform = item["properties"]["proj:transform"]
        cell = (round(transform[2]), round(transform[5]) - 1)  # (west, south) of the 1-degree tile
        if cell not in dem_cells:
            continue
        href = item["assets"]["data"]["href"]
        target = root / "rasters" / "dem" / href.rsplit("/", 1)[-1]
        if not target.exists():
            download(_sign(href, session), target, session)
        dem_files.append(target)
    log(f"  rasters: {len(gsw_files)} surface-water tiles, {len(dem_files)} DEM tiles")
    return {
        "jrc_gsw": {"tiles": len(gsw_files), "size_bytes": sum(p.stat().st_size for p in gsw_files),
                    "licence": "Copernicus Programme, free of charge without restriction of use. Source: EC JRC/Google",
                    "observation_period": "1984-03 to 2021-12 (Landsat 5, 7, 8)", "resolution": "~30 m"},
        "copernicus_dem": {"tiles": len(dem_files), "size_bytes": sum(p.stat().st_size for p in dem_files),
                           "licence": ("Copernicus DEM licence (free use). (c) DLR e.V. 2010-2014 and (c) Airbus Defence "
                                       "and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA"),
                           "product_date": "2021-04-22", "observation_period": "TanDEM-X acquisitions 2011-2015",
                           "resolution": "~30 m surface model (includes buildings and trees)"},
    }


# --- region build ----------------------------------------------------------------------

def build_region(name: str, root: Path, session: requests.Session) -> None:
    import shapely
    from shapely.geometry import mapping

    catalogue = region_catalogue(root)
    if name not in catalogue:
        raise SystemExit(f"Unknown region {name!r}. Known regions: {', '.join(sorted(catalogue))}")
    states = load_states(root)
    members = [states[iso] for iso in catalogue[name]]
    coverage = shapely.union_all([member["geometry"] for member in members])
    label = REGION_LABELS.get(name) or " and ".join(member["name"] for member in members)
    log(f"Region {name}: {label}")

    zone = zone_for(coverage, root, session)
    downloads = root / "downloads"
    existing = sorted(downloads.glob(f"{zone}-*.osm.pbf"))
    if existing:
        pbf = existing[-1]
        log(f"  reusing the extract already on disk: {pbf.name} (delete it to fetch a newer one)")
    else:
        latest = f"{GEOFABRIK}/{zone}-latest.osm.pbf"
        head = session.head(latest, allow_redirects=False, timeout=30)
        resolved = head.headers.get("Location") or latest
        size = int(session.head(resolved, timeout=30).headers.get("Content-Length") or 0)
        check_disk(root, size + 1_500_000_000)
        pbf = download(resolved, downloads / resolved.rsplit("/", 1)[-1], session)

    log("Caching surface-water and DEM tiles for the region ...")
    rasters = fetch_rasters(coverage, root, session)
    directory = root / "regions" / name
    osm = build_osm(pbf, coverage, directory)
    (directory / REGION_BOUNDARY).write_text(json.dumps({
        "type": "Feature",
        "properties": {"name": label, "states": catalogue[name], "source": "geoBoundaries gbOpen IND ADM1"},
        "geometry": mapping(coverage),
    }), encoding="utf-8")
    manifest = {"label": label, "states": catalogue[name], "geofabrik_zone": zone, "osm": osm, **rasters,
                "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    (directory / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"Region {name} ready: {directory}")


def list_regions(root: Path) -> None:
    catalogue = region_catalogue(root)
    installed = {path.name for path in (root / "regions").glob("*") if (path / REGION_STORE).exists()}
    print("Regions (installed marked *):")
    for name in sorted(catalogue):
        print(f"  {'*' if name in installed else ' '} {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("region", nargs="?", help="region slug, e.g. tamil-nadu or andhra-pradesh")
    parser.add_argument("--list", action="store_true", help="list regions and exit")
    parser.add_argument("--data-dir", type=Path, default=None)
    args = parser.parse_args()
    root = (args.data_dir or data_root()).resolve()
    session = requests.Session()
    migrate_legacy(root)
    install_india(root, session)
    if args.list or not args.region:
        list_regions(root)
        if not args.region:
            print("\nAnalyses already work India-wide. Add a region for local accessibility data: "
                  "terrascope.cmd fetch-data <region>")
        return
    build_region(args.region, root, session)


if __name__ == "__main__":
    main()

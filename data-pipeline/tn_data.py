"""Download and build TerraScope's local Tamil Nadu evidence data.

    python tn_data.py [--data-dir DIR]          (run by: terrascope.cmd fetch-data)

Produces, in a git-ignored folder (default <repo>/tn-data):
  tn_osm.sqlite        roads, schools, hospitals, bus, rail stations, waterways and
                       water bodies clipped to Tamil Nadu (+5 km), R*Tree indexed
  tn_boundary.geojson  coverage polygon: Tamil Nadu minus Puducherry/Karaikal
  gsw/                 JRC Global Surface Water v1.4 occurrence + extent tiles
  dem/                 Copernicus DEM GLO-30 tiles covering Tamil Nadu
  manifest.json        source, licence, data date and size of every dataset

Re-running skips files already downloaded and rebuilds the OSM store.
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
from connectors.local_osm import BOUNDARY_NAME, MANIFEST_NAME, STORE_NAME, create_store, data_dir, write_features  # noqa: E402


GEOFABRIK_PBF = "https://download.geofabrik.de/asia/india/southern-zone-latest.osm.pbf"
GSW_BASE = "https://storage.googleapis.com/global-surface-water/downloads2021"
# JRC tiles are 10 x 10 degrees, named by their north-west corner.
GSW_TILES = ("70E_20N", "80E_20N", "70E_10N", "80E_10N")
PC_STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
PC_SIGN = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"
# Tamil Nadu's extent plus a margin, so border parcels still see features next door.
TN_BBOX = (76.0, 7.9, 80.6, 13.8)
CLIP_BUFFER_DEG = 0.05  # ~5 km

USER_AGENT = "TerraScope/0.1 (local data build)"
NON_ROAD = {
    "footway", "path", "steps", "cycleway", "bridleway", "corridor", "pedestrian", "platform",
    "proposed", "construction", "raceway", "escape", "elevator", "service", "track", "bus_stop",
}
WATERWAYS = {"river", "canal", "drain", "stream", "ditch", "tidal_channel"}
ESTIMATED_NEED_BYTES = 3_500_000_000  # downloads + built store + headroom


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


def check_disk(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(directory).free
    log(f"Free disk at {directory}: {free / 1e9:.1f} GB (need about {ESTIMATED_NEED_BYTES / 1e9:.1f} GB)")
    if free < ESTIMATED_NEED_BYTES:
        raise SystemExit("Not enough free disk space; nothing was downloaded or deleted.")


# --- OpenStreetMap -------------------------------------------------------------

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


def build_osm(pbf: Path, directory: Path) -> dict:
    import osmium
    import shapely
    from shapely import wkb as shapely_wkb

    as_of = osmium.FileProcessor(str(pbf)).header.get("osmosis_replication_timestamp") or ""
    log(f"Building local OSM store from {pbf.name} (data up to {as_of or 'unknown'}) ...")

    factory = osmium.geom.WKBFactory()
    tmp = directory / (STORE_NAME + ".building")
    tmp.unlink(missing_ok=True)
    connection = create_store(tmp)
    min_lon, min_lat, max_lon, max_lat = TN_BBOX
    boundaries: dict[str, object] = {}
    batch: list[tuple] = []
    counts: dict[str, int] = {}
    skipped = 0
    started = time.monotonic()

    processor = (
        osmium.FileProcessor(str(pbf))
        .with_locations()
        .with_areas(osmium.filter.KeyFilter("natural", "landuse", "amenity", "healthcare", "boundary", "railway", "waterway"))
        .with_filter(osmium.filter.KeyFilter(
            "highway", "amenity", "healthcare", "railway", "waterway", "natural", "landuse", "boundary"))
    )
    for obj in processor:
        tags = obj.tags
        if obj.is_area() and tags.get("boundary") == "administrative" and tags.get("admin_level") == "4":
            name = tags.get("name:en") or tags.get("name")
            if name in ("Tamil Nadu", "Puducherry"):
                boundaries[name] = (shapely_wkb.loads(factory.create_multipolygon(obj), hex=True), obj.orig_id())
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

    if "Tamil Nadu" not in boundaries or "Puducherry" not in boundaries:
        raise RuntimeError(f"Admin boundaries missing from the extract: found {sorted(boundaries)}")
    tamil_nadu, tn_relation = boundaries["Tamil Nadu"]
    puducherry, py_relation = boundaries["Puducherry"]
    if not tamil_nadu.is_valid:
        tamil_nadu = shapely.make_valid(tamil_nadu)
    if not puducherry.is_valid:
        puducherry = shapely.make_valid(puducherry)
    # Subtract Puducherry explicitly rather than trusting inner rings on the TN relation.
    covered = tamil_nadu.difference(puducherry)

    log("Clipping features to Tamil Nadu + 5 km ...")
    clip = covered.buffer(CLIP_BUFFER_DEG)
    shapely.prepare(clip)
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
        "source": "OpenStreetMap, Geofabrik southern-zone extract",
        "source_url": GEOFABRIK_PBF,
        "licence": "ODbL 1.0 - (c) OpenStreetMap contributors",
        "data_as_of": as_of,
        "extract_file": pbf.name,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    connection.executemany("INSERT OR REPLACE INTO store_meta VALUES (?, ?)", list(meta.items()))
    connection.commit()
    connection.execute("VACUUM")
    connection.close()
    target = directory / STORE_NAME
    tmp.replace(target)

    boundary = {
        "type": "Feature",
        "properties": {
            "name": "Tamil Nadu (Puducherry and Karaikal enclaves excluded)",
            "source": f"OpenStreetMap relations {tn_relation} (Tamil Nadu) minus {py_relation} (Puducherry), Geofabrik southern-zone extract",
            "licence": "ODbL 1.0 - (c) OpenStreetMap contributors",
            "data_as_of": as_of,
        },
        "geometry": shapely.geometry.mapping(covered),
    }
    (directory / BOUNDARY_NAME).write_text(json.dumps(boundary), encoding="utf-8")
    log(f"OSM store: {layer_counts}; {removed:,} outside the clip removed; {skipped} broken geometries skipped; "
        f"{target.stat().st_size / 1e6:.0f} MB in {time.monotonic() - started:.0f}s")
    return {**meta, "layers": layer_counts, "size_bytes": target.stat().st_size,
            "boundary_relations": {"tamil_nadu": tn_relation, "puducherry": py_relation}}


# --- rasters -------------------------------------------------------------------

def fetch_gsw(directory: Path, session: requests.Session) -> dict:
    files = []
    for layer in ("occurrence", "extent"):
        for tile in GSW_TILES:
            name = f"{layer}_{tile}v1_4_2021.tif"
            files.append(download(f"{GSW_BASE}/{layer}/{name}", directory / "gsw" / name, session))
    return {
        "source": "JRC Global Surface Water v1.4 (Pekel et al. 2016, Nature 540)",
        "source_url": GSW_BASE,
        "licence": "Copernicus Programme, free of charge without restriction of use. Attribution: Source: EC JRC/Google",
        "observation_period": "1984-03 to 2021-12 (Landsat 5, 7, 8)",
        "resolution": "1 arc-second (~30 m)",
        "layers": ["occurrence", "extent"],
        "size_bytes": sum(path.stat().st_size for path in files),
    }


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


def fetch_dem(directory: Path, session: requests.Session) -> dict:
    min_lon, min_lat, max_lon, max_lat = TN_BBOX
    response = session.post(PC_STAC, json={
        "collections": ["cop-dem-glo-30"], "bbox": [min_lon, min_lat, max_lon, max_lat], "limit": 200,
    }, timeout=60)
    response.raise_for_status()
    items = response.json()["features"]
    files, dates = [], set()
    for item in items:
        href = item["assets"]["data"]["href"]
        target = directory / "dem" / href.rsplit("/", 1)[-1]
        if not target.exists():
            download(_sign(href, session), target, session)
        files.append(target)
        dates.add(item["properties"].get("datetime", "")[:10])
    log(f"  DEM: {len(files)} tiles")
    return {
        "source": "Copernicus DEM GLO-30, via Microsoft Planetary Computer (collection cop-dem-glo-30)",
        "licence": ("Copernicus DEM licence (free use). (c) DLR e.V. 2010-2014 and (c) Airbus Defence and "
                    "Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved"),
        "product_date": sorted(dates)[-1] if dates else None,
        "observation_period": "TanDEM-X acquisitions 2011-2015",
        "resolution": "1 arc-second (~30 m) surface model (includes buildings and trees)",
        "tiles": len(files),
        "size_bytes": sum(path.stat().st_size for path in files),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=None)
    args = parser.parse_args()
    directory = (args.data_dir or data_dir()).resolve()
    check_disk(directory)
    session = requests.Session()

    log("Downloading the Geofabrik southern-zone extract ...")
    # Resolve "latest" to its dated file so the manifest names the exact extract.
    resolved = session.head(GEOFABRIK_PBF, allow_redirects=False, timeout=30).headers.get("Location") or GEOFABRIK_PBF
    pbf = download(resolved, directory / "downloads" / resolved.rsplit("/", 1)[-1], session)
    for stale in (directory / "downloads").glob("southern-zone-*.osm.pbf"):
        if stale != pbf:
            log(f"  older extract kept: {stale.name} (delete it by hand if unwanted)")

    manifest = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    log("Downloading JRC Global Surface Water tiles ...")
    manifest["jrc_gsw"] = fetch_gsw(directory, session)
    log("Downloading Copernicus DEM tiles ...")
    manifest["copernicus_dem"] = fetch_dem(directory, session)
    manifest["osm"] = build_osm(pbf, directory)
    manifest["osm"]["download_bytes"] = pbf.stat().st_size
    (directory / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"Done. Manifest: {directory / MANIFEST_NAME}")


if __name__ == "__main__":
    main()

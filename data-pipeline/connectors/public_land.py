"""Public facilities and possibly restricted land near a parcel, from OpenStreetMap.

What this is: mapping evidence. A court, stadium, railway yard, park, defence area or water body drawn in OpenStreetMap
that overlaps or adjoins the user's boundary. What it is not: ownership. A stadium is a sports facility, not proof that
the land is government-owned; a mapped overlap is not proof that the plot belongs to anyone. Ownership comes only from
official land records (see ``backend-api/routers/legal_checks.py``), and none is read automatically.

Contact is measured on the real parcel geometry, never its centre:
  overlap       the feature covers a material part of the plot (>= 200 m2 or >= 5 %), or a railway line crosses it
  point_inside  a facility mapped only as a point lies inside the plot (its extent is unknown)
  edge          it touches the plot, or lies within the positional uncertainty (15 m) of OSM and a hand-drawn boundary
  nearby        within 2 km; proximity only
No authoritative public-land boundary (cadastral / poramboke geometry) is available for any state, so every finding
here is "mapped", never "confirmed". A missing feature means nothing was mapped, not that the land is private.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import shapely
from shapely.geometry import mapping, shape

STORE_NAME = "public_land.sqlite"
NEARBY_M = 2000.0
UNCERTAINTY_M = 15.0  # OSM features in India are often 5-15 m off, and the boundary is hand-drawn
OVERLAP_MIN_M2 = 200.0
OVERLAP_MIN_SHARE = 0.05
LINE_MIN_M = 10.0
STALE_AFTER_DAYS = 365

CATEGORIES = {
    "court": "Court",
    "government_office": "Government office or public service (police, fire, town hall)",
    "government_school": "Government school (identified from its name or operator tag)",
    "government_hospital": "Government hospital (identified from its name or operator tag)",
    "sports": "Stadium or sports ground",
    "park": "Public park or playground",
    "railway_land": "Railway land",
    "railway_station": "Railway station",
    "railway_track": "Railway line",
    "defence": "Defence / military area",
    "protected_area": "Protected or reserved area",
    "burial_ground": "Burial ground or cemetery",
    "water_body": "Water body (lake, tank, reservoir, river)",
}
GOVERNMENT_NAME = re.compile(r"\b(govt\.?|government|panchayat union|municipal|corporation|district head ?quarters?)\b", re.I)
TAG_KEYS = ("name", "name:en", "operator", "operator:type", "ownership", "government", "military", "landuse", "leisure",
            "amenity", "office", "railway", "boundary", "access", "start_date")


def classify(tags: Any, is_area: bool, is_node: bool, is_way: bool) -> list[tuple[str, str]]:
    """(category, kind) pairs for one OSM object. Facility type only: ownership is never inferred from it."""
    get = tags.get
    out: list[tuple[str, str]] = []
    amenity, leisure, landuse, railway = get("amenity"), get("leisure"), get("landuse"), get("railway")
    if is_way and not is_area and railway in ("rail", "light_rail", "subway", "narrow_gauge"):
        out.append(("railway_track", railway))
    if not (is_node or is_area):
        return out
    operator = f"{get('operator') or ''} {get('name:en') or get('name') or ''}"
    # operator:type=public is used loosely in Indian OSM ("open to the public": a private clinic run by "Dr. Arun" was
    # tagged so), so only operator:type=government or a government name counts.
    public_operator = get("operator:type") == "government" or bool(GOVERNMENT_NAME.search(operator))
    if amenity == "courthouse":
        out.append(("court", "courthouse"))
    if get("office") == "government" or get("government") or amenity in ("townhall", "police", "fire_station", "prison"):
        out.append(("government_office", amenity or get("government") or "government"))
    if amenity == "school" and public_operator:
        out.append(("government_school", "school"))
    if amenity == "hospital" and public_operator:
        out.append(("government_hospital", "hospital"))
    # A sports centre is most often a private academy or gym; only a government-run one is a public-land signal.
    if leisure in ("stadium", "recreation_ground") or (leisure == "sports_centre" and public_operator):
        out.append(("sports", leisure))
    if leisure in ("park", "playground"):
        out.append(("park", leisure))
    if landuse == "railway":
        out.append(("railway_land", "landuse=railway"))
    if railway == "station":
        out.append(("railway_station", "station"))
    if landuse == "military" or (get("military") and get("military") != "no"):
        out.append(("defence", get("military") or "landuse=military"))
    if get("boundary") in ("protected_area", "national_park") or leisure == "nature_reserve":
        out.append(("protected_area", get("protect_class") or get("boundary") or leisure))
    if landuse == "cemetery" or amenity == "grave_yard":
        out.append(("burial_ground", landuse or amenity))
    return out


def ownership_signal(tags: dict[str, Any], category: str) -> tuple[str, str]:
    """What the map's own tags say about the operator or owner, kept apart from the facility type."""
    op_type, ownership = tags.get("operator:type"), tags.get("ownership")
    if category == "defence" or tags.get("landuse") == "military":
        return "government_tagged", "mapped as military land"
    if ownership in ("national", "state", "municipal", "public", "government") or op_type in ("government", "military"):
        return "government_tagged", f"tagged {'ownership=' + ownership if ownership else 'operator:type=' + op_type}"
    if tags.get("office") == "government" or tags.get("government"):
        return "government_tagged", "tagged as a government office"
    if ownership == "private" or op_type == "private":
        return "private_tagged", "tagged as privately operated"
    if category in ("government_school", "government_hospital") and tags.get("operator"):
        return "government_tagged", f"operator {tags['operator']}"
    return "unknown", "no operator or ownership tag"


def _projector(lon0: float, lat0: float):
    scale_lon, scale_lat = 111_320.0 * math.cos(math.radians(lat0)), 110_574.0

    def forward(coords):
        out = coords.copy()
        out[:, 0] = (coords[:, 0] - lon0) * scale_lon
        out[:, 1] = (coords[:, 1] - lat0) * scale_lat
        return out

    return forward, scale_lon, scale_lat


def contact(feature, parcel, distance: float) -> tuple[str, float, float]:
    """(contact, overlap_m2 or crossing length, share of the parcel) for metre-projected geometries."""
    if feature.geom_type in ("Polygon", "MultiPolygon"):
        area = feature.intersection(parcel).area if distance == 0 else 0.0
        share = area / parcel.area if parcel.area else 0.0
        if area >= OVERLAP_MIN_M2 or share >= OVERLAP_MIN_SHARE:
            return "overlap", round(area, 1), round(share, 4)
        return ("edge" if distance <= UNCERTAINTY_M else "nearby"), round(area, 1), round(share, 4)
    if feature.geom_type in ("LineString", "MultiLineString"):
        length = feature.intersection(parcel).length if distance == 0 else 0.0
        if length >= LINE_MIN_M:
            return "overlap", round(length, 1), 0.0
        return ("edge" if distance <= UNCERTAINTY_M else "nearby"), round(length, 1), 0.0
    if distance == 0:
        return "point_inside", 0.0, 0.0
    return ("edge" if distance <= UNCERTAINTY_M else "nearby"), 0.0, 0.0


def _rows(path: Path, box: tuple[float, float, float, float], layers: tuple[str, ...] | None) -> tuple[list[tuple], dict]:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        west, south, east, north = box
        sql = ("SELECT f.layer, f.class, f.name, f.osm_id, f.tags, f.geom FROM features_rtree r JOIN features f ON f.id = r.id "
               "WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ?")
        params: list[Any] = [east, west, north, south]
        if layers:
            sql += f" AND f.layer IN ({','.join('?' * len(layers))})"
            params += list(layers)
        rows = connection.execute(sql, params).fetchall()
        meta = dict(connection.execute("SELECT key, value FROM store_meta").fetchall())
    finally:
        connection.close()
    return rows, meta


def assess(geojson_polygon: dict[str, Any], store: Path | None, water_store: Path | None = None,
           now: datetime | None = None) -> dict[str, Any]:
    """Mapped public facilities touching or near the parcel. Never an ownership finding."""
    now = now or datetime.now(timezone.utc)
    base = {"authoritative_boundaries": None, "uncertainty_m": UNCERTAINTY_M, "search_radius_m": NEARBY_M,
            "limitations": ("OpenStreetMap shows what volunteers have mapped: facilities can be missing, mis-placed by "
                            f"{UNCERTAINTY_M:.0f} m or more, or outdated. A facility type is not an owner, an overlap "
                            "is not proof of ownership, and finding nothing is not proof that the land is private or "
                            "unrestricted. No official public-land boundary is available to compare with.")}
    if store is None or not Path(store).exists():
        return {**base, "status": "unavailable", "overlaps": [], "nearby": [],
                "reason": "The public-facility map for this region is not built. Build it with: "
                          "python data-pipeline/fetch_data.py <region> --public-land"}
    parcel_ll = shape(geojson_polygon)
    lon0, lat0 = parcel_ll.centroid.x, parcel_ll.centroid.y
    forward, scale_lon, scale_lat = _projector(lon0, lat0)
    parcel = shapely.transform(parcel_ll, forward)
    west, south, east, north = parcel_ll.bounds
    box = (west - NEARBY_M / scale_lon, south - NEARBY_M / scale_lat, east + NEARBY_M / scale_lon, north + NEARBY_M / scale_lat)
    rows, meta = _rows(Path(store), box, None)
    if water_store is not None and Path(water_store).exists():
        rows += [("water_body", *row[1:]) for row in _rows(Path(water_store), box, ("water",))[0]]
    items = []
    for layer, kind, name, osm_id, tags_json, geom in rows:
        feature_ll = shapely.from_wkb(geom)
        feature = shapely.transform(feature_ll, forward)
        distance = float(feature.distance(parcel))
        if distance > NEARBY_M:
            continue
        tags = json.loads(tags_json or "{}")
        touch, measure, share = contact(feature, parcel, distance)
        signal, basis = ownership_signal(tags, layer)
        item = {"category": layer, "category_label": CATEGORIES.get(layer, layer), "kind": kind, "name": name,
                "osm_id": osm_id, "contact": touch, "distance_m": round(distance, 1), "overlap_m2": measure if touch != "nearby" else 0.0,
                "overlap_share": share, "ownership_signal": signal, "ownership_basis": basis,
                # A point on the feature, for a map marker.
                "lat": round(feature_ll.representative_point().y, 6), "lon": round(feature_ll.representative_point().x, 6)}
        if touch != "nearby":  # small enough to draw on the map
            item["geometry"] = mapping(feature_ll.simplify(0.00002, preserve_topology=True))
        items.append(item)
    contacts = sorted((i for i in items if i["contact"] != "nearby"), key=lambda i: (i["contact"] != "overlap", -i["overlap_share"]))
    nearest: dict[str, dict[str, Any]] = {}
    for item in sorted((i for i in items if i["contact"] == "nearby"), key=lambda i: i["distance_m"]):
        nearest.setdefault(item["category"], item)
    as_of = (meta.get("data_as_of") or "")[:10]
    stale = None
    try:
        stale = (now - datetime.fromisoformat(as_of).replace(tzinfo=timezone.utc)).days > STALE_AFTER_DAYS
    except ValueError:
        pass
    return {**base, "status": "assessed", "overlaps": contacts, "nearby": sorted(nearest.values(), key=lambda i: i["distance_m"]),
            "source": meta.get("source") or "OpenStreetMap", "licence": meta.get("licence"), "data_as_of": as_of or None,
            "stale": stale}


def build_store(pbf: Path, coverage, directory: Path, log=print) -> dict[str, Any]:
    """Public-facility store for one region from the extract already on disk (no download)."""
    import time

    import osmium
    from shapely import wkb as shapely_wkb

    from connectors.local_osm import create_store, write_features

    as_of = osmium.FileProcessor(str(pbf)).header.get("osmosis_replication_timestamp") or ""
    factory = osmium.geom.WKBFactory()
    directory.mkdir(parents=True, exist_ok=True)
    tmp = directory / (STORE_NAME + ".building")
    tmp.unlink(missing_ok=True)
    connection = create_store(tmp)
    clip = coverage.buffer(0.05)
    shapely.prepare(clip)
    min_lon, min_lat, max_lon, max_lat = clip.bounds
    keys = ("amenity", "office", "government", "leisure", "landuse", "military", "railway", "boundary")
    processor = (osmium.FileProcessor(str(pbf)).with_locations()
                 .with_areas(osmium.filter.KeyFilter(*keys)).with_filter(osmium.filter.KeyFilter(*keys)))
    batch, counts, skipped, started = [], {}, 0, time.monotonic()
    for obj in processor:
        layers = classify(obj.tags, obj.is_area(), obj.is_node(), obj.is_way())
        if not layers:
            continue
        try:
            hexwkb = (factory.create_point(obj) if obj.is_node() else
                      factory.create_multipolygon(obj) if obj.is_area() else factory.create_linestring(obj))
            geometry = shapely_wkb.loads(hexwkb, hex=True)
        except Exception:  # broken or incomplete OSM geometry
            skipped += 1
            continue
        x0, y0, x1, y1 = geometry.bounds
        if x1 < min_lon or x0 > max_lon or y1 < min_lat or y0 > max_lat or not clip.intersects(geometry):
            continue
        osm_id = (f"{'w' if obj.from_way() else 'r'}{obj.orig_id()}" if obj.is_area()
                  else f"{'n' if obj.is_node() else 'w'}{obj.id}")
        keep = {k: obj.tags.get(k) for k in TAG_KEYS if obj.tags.get(k)}
        for layer, kind in layers:
            batch.append((layer, kind, obj.tags.get("name:en") or obj.tags.get("name"), osm_id, keep, geometry))
            counts[layer] = counts.get(layer, 0) + 1
        if len(batch) >= 20_000:
            write_features(connection, batch)
            batch.clear()
    write_features(connection, batch)
    meta = {"source": "OpenStreetMap, Geofabrik India zone extract", "extract_file": pbf.name, "data_as_of": as_of,
            "licence": "ODbL 1.0 - (c) OpenStreetMap contributors",
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    connection.executemany("INSERT OR REPLACE INTO store_meta VALUES (?, ?)", list(meta.items()))
    connection.commit()
    connection.execute("VACUUM")
    connection.close()
    target = directory / STORE_NAME
    tmp.replace(target)
    log(f"Public-facility store: {counts}; {skipped} broken geometries skipped; "
        f"{target.stat().st_size / 1e6:.1f} MB in {time.monotonic() - started:.0f}s")
    return {**meta, "layers": counts, "size_bytes": target.stat().st_size}
